"""Standalone certificate verification tool.

Usage:
  python verify_tool.py verify-file --file certificates/Alice_Smith.pdf [--token <token>] [--mongo-uri <uri>]
  python verify_tool.py verify-db --cert-id <CERT-ID> --name "Name" --course "Course" [--token <token>] [--mongo-uri <uri>]

This script reads embedded metadata created by `certificate_generator.py` and
verifies authenticity by cross-checking with MongoDB (if available) or by
inspecting embedded token_hash/checksum.
"""
import os
import json
import hashlib
import hmac
from typing import Optional

import click

try:
    from PyPDF2 import PdfReader
    _HAS_PYPDF = True
except Exception:
    PdfReader = None
    _HAS_PYPDF = False

try:
    from pymongo import MongoClient
    _HAS_PYMONGO = True
except Exception:
    MongoClient = None
    _HAS_PYMONGO = False


def generate_checksum(data: dict, secret: Optional[str] = None) -> str:
    if secret is None:
        secret = os.getenv("CERT_SECRET", "default-secret")
    s = json.dumps(data, sort_keys=True)
    return hmac.new(secret.encode(), s.encode(), hashlib.sha256).hexdigest()[:16]


def extract_payload_from_pdf(pdf_path: str) -> Optional[dict]:
    if not _HAS_PYPDF:
        raise RuntimeError("PyPDF2 is not installed. Install with: pip install PyPDF2")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(pdf_path)

    reader = PdfReader(pdf_path)
    info = reader.metadata or {}
    # Try several keys depending on PyPDF2 version
    creator = info.get('/Creator') or info.get('Creator') or info.get('producer') or ''
    if not creator or 'CertGen|' not in creator:
        return None

    raw = creator.split('CertGen|', 1)[1]
    try:
        payload = json.loads(raw)
        return payload
    except Exception:
        # attempt to recover JSON substring
        start = raw.find('{')
        end = raw.rfind('}')
        if start == -1 or end == -1:
            return None
        try:
            payload = json.loads(raw[start:end+1])
            return payload
        except Exception:
            return None


def connect_mongo(uri: Optional[str] = None):
    if not _HAS_PYMONGO:
        raise RuntimeError("pymongo not installed. Install with: pip install pymongo")
    uri = uri or os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    # quick ping
    client.admin.command('ping')
    db = client['certificate_db']
    coll = db['certificates']
    return client, coll


@click.group()
def cli():
    pass


@cli.command('verify-file')
@click.option('--file', 'file_path', required=True, type=click.Path(exists=True), help='PDF file to verify')
@click.option('--token', default=None, help='Verification token (optional)')
@click.option('--mongo-uri', default=None, help='MongoDB URI (optional)')
def verify_file(file_path: str, token: Optional[str], mongo_uri: Optional[str]):
    """Verify a certificate PDF using embedded metadata and optional MongoDB."""
    try:
        payload = extract_payload_from_pdf(file_path)
    except RuntimeError as e:
        click.secho(str(e), fg='red')
        return
    except FileNotFoundError:
        click.secho(f"File not found: {file_path}", fg='red')
        return

    if not payload:
        click.secho('No embedded certificate metadata found in PDF', fg='red')
        return

    cert_id = payload.get('id')
    token_hash = payload.get('token_hash')
    checksum = payload.get('checksum')

    # If MongoDB available, use it
    if mongo_uri or os.getenv('MONGODB_URI'):
        try:
            client, coll = connect_mongo(mongo_uri)
        except Exception as e:
            click.secho(f"MongoDB connection failed: {e}", fg='yellow')
            client = coll = None
    else:
        client = coll = None

    if coll:
        record = coll.find_one({'certificate_id': cert_id})
        if not record:
            click.secho('Certificate ID not found in database', fg='red')
            if client:
                client.close()
            return

        # token check
        if token:
            token_hash_local = hashlib.sha256(token.encode()).hexdigest()
            if token_hash_local != record.get('credentials', {}).get('token_hash'):
                click.secho('Token mismatch', fg='red')
                if client:
                    client.close()
                return

        # checksum verification
        recompute = {
            'certificate_id': record.get('certificate_id'),
            'recipient_name': record.get('recipient_name'),
            'course_name': record.get('course_name'),
            'issue_date': record.get('issue_date'),
            'issuer': record.get('issuer'),
            'generated_at': record.get('generated_at'),
        }
        expected = generate_checksum(recompute)
        stored = record.get('credentials', {}).get('checksum')
        if stored and expected != stored:
            click.secho('Checksum mismatch - data differs from DB', fg='red')
            if client:
                client.close()
            return

        click.secho('✓ Certificate VERIFIED (DB)', fg='green')
        click.echo(f'  ID: {cert_id}')
        click.echo(f'  Recipient: {record.get("recipient_name")}')
        click.echo(f'  Course: {record.get("course_name")}')
        if client:
            client.close()
        return

    # Try a local JSON store file named credentials.json
    from pathlib import Path
    local_file = Path('credentials.json')
    if local_file.exists():
        try:
            with local_file.open('r', encoding='utf-8') as f:
                records = json.load(f)
                local_rec = next((r for r in records if r.get('certificate_id') == cert_id), None)
        except Exception:
            local_rec = None

        if local_rec:
            if token:
                token_hash_local = hashlib.sha256(token.encode()).hexdigest()
                if token_hash_local != local_rec.get('credentials', {}).get('token_hash'):
                    click.secho('Token mismatch (local store)', fg='red')
                    return

            recompute = {
                'certificate_id': local_rec.get('certificate_id'),
                'recipient_name': local_rec.get('recipient_name'),
                'course_name': local_rec.get('course_name'),
                'issue_date': local_rec.get('issue_date'),
                'issuer': local_rec.get('issuer'),
                'generated_at': local_rec.get('generated_at'),
            }
            expected = generate_checksum(recompute)
            stored = local_rec.get('credentials', {}).get('checksum')
            if stored and expected != stored:
                click.secho('Checksum mismatch - data differs from local store', fg='red')
                return

            click.secho('✓ Certificate VERIFIED (local store)', fg='green')
            click.echo(f'  ID: {cert_id}')
            click.echo(f'  Recipient: {local_rec.get("recipient_name")}')
            click.echo(f'  Course: {local_rec.get("course_name")}')
            return

    # Fallback to metadata-only check
    if token:
        token_hash_local = hashlib.sha256(token.encode()).hexdigest()
        if token_hash_local != token_hash:
            click.secho('Token mismatch (metadata)', fg='red')
            return

    if checksum:
        click.secho('✓ Certificate contains embedded credential checksum', fg='green')
        click.echo(f'  ID: {cert_id}')
        click.echo('  Note: Full verification requires access to stored certificate fields or a local store')
        return

    click.secho('Insufficient embedded metadata to verify certificate', fg='red')


@cli.command('verify-db')
@click.option('--cert-id', required=True, help='Certificate ID')
@click.option('--name', required=True, help='Recipient name')
@click.option('--course', default=None, help='Course name (optional)')
@click.option('--token', default=None, help='Verification token (optional)')
@click.option('--mongo-uri', default=None, help='MongoDB URI')
def verify_db(cert_id: str, name: str, course: Optional[str], token: Optional[str], mongo_uri: Optional[str]):
    """Verify certificate directly against MongoDB by ID and fields."""
    # Prefer MongoDB when provided, otherwise fall back to local JSON store
    client = coll = None
    if mongo_uri or os.getenv('MONGODB_URI'):
        try:
            client, coll = connect_mongo(mongo_uri)
        except Exception as e:
            click.secho(f'MongoDB connection failed: {e}', fg='yellow')
            client = coll = None

    record = None
    if coll:
        record = coll.find_one({'certificate_id': cert_id})
    else:
        # Try local credentials.json
        from pathlib import Path
        local_file = Path('credentials.json')
        if local_file.exists():
            try:
                with local_file.open('r', encoding='utf-8') as f:
                    records = json.load(f)
                    record = next((r for r in records if r.get('certificate_id') == cert_id), None)
            except Exception:
                record = None

    if not record:
        click.secho('Certificate not found', fg='red')
        if client:
            client.close()
        return

    if record.get('recipient_name') != name:
        click.secho('Recipient name mismatch', fg='red')
        if client:
            client.close()
        return

    if record.get('course_name') != course:
        click.secho('Course name mismatch', fg='red')
        if client:
            client.close()
        return

    if token:
        token_hash_local = hashlib.sha256(token.encode()).hexdigest()
        if token_hash_local != record.get('credentials', {}).get('token_hash'):
            click.secho('Token mismatch', fg='red')
            if client:
                client.close()
            return

    # checksum
    recompute = {
        'certificate_id': record.get('certificate_id'),
        'recipient_name': record.get('recipient_name'),
        'course_name': record.get('course_name'),
        'issue_date': record.get('issue_date'),
        'issuer': record.get('issuer'),
        'generated_at': record.get('generated_at'),
    }
    expected = generate_checksum(recompute)
    stored = record.get('credentials', {}).get('checksum')
    if stored and expected != stored:
        click.secho('Checksum mismatch - data differs', fg='red')
        if client:
            client.close()
        return

    click.secho('✓ Certificate VERIFIED', fg='green')
    click.echo(f'  ID: {cert_id}')
    click.echo(f'  Recipient: {record.get("recipient_name")}')
    click.echo(f'  Course: {record.get("course_name")}')
    if client:
        client.close()


if __name__ == '__main__':
    cli()
