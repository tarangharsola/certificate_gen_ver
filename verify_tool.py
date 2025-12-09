import os
import json
import hashlib
import hmac
from typing import Optional
import click

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None


def generate_checksum(data: dict, secret: Optional[str] = None) -> str:
    if secret is None:
        secret = os.getenv("CERT_SECRET", "default-secret")
    s = json.dumps(data, sort_keys=True)
    return hmac.new(secret.encode(), s.encode(), hashlib.sha256).hexdigest()[:16]


def extract_payload_from_pdf(pdf_path: str):
    if PdfReader is None:
        raise RuntimeError("Install PyPDF2 first")

    reader = PdfReader(pdf_path)
    info = reader.metadata or {}

    for v in info.values():
        if isinstance(v, str) and "CertGen|" in v:
            raw = v.split("CertGen|", 1)[1]
            return json.loads(raw)

    return None


def load_local_record(cert_id):
    from pathlib import Path
    p = Path("credentials.json")
    if not p.exists():
        return None

    with p.open("r", encoding="utf-8") as f:
        records = json.load(f)

    return next((r for r in records if r.get("certificate_id") == cert_id), None)


@click.group()
def cli():
    pass


@cli.command("verify-file")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True))
def verify_file(file_path):

    payload = extract_payload_from_pdf(file_path)
    if not payload:
        click.secho("✗ No embedded certificate metadata found in PDF", fg="red")
        click.echo("  (Metadata and QR code may be missing or were not generated.)")
        return

    cert_id = payload["id"]
    embedded_token_hash = payload["token_hash"]
    embedded_checksum = payload["checksum"]
    has_qr = payload.get("has_qr", False)

    record = load_local_record(cert_id)
    if not record:
        click.secho("✗ Certificate not found in the database", fg="red")
        return

    if record["credentials"]["token_hash"] != embedded_token_hash:
        click.secho("✗ Certificate is not authentic", fg="red")
        return

    expected = generate_checksum({
        "certificate_id": record["certificate_id"],
        "recipient_name": record["recipient_name"],
        "issue_date": record["issue_date"],
        "issuer": record["issuer"],
        "title": record["title"],
        "generated_at": record["generated_at"],
    })

    if expected != embedded_checksum:
        click.secho("✗ PDF tampered", fg="red")
        return

    click.secho("✓ Certificate VERIFIED", fg="green")
    click.echo(f"  Certificate ID : {cert_id}")
    click.echo(f"  Recipient      : {record['recipient_name']}")
    click.echo(f"  Issue Date     : {record['issue_date']}")
    click.echo(f"  QR Code        : {'PRESENT' if has_qr else 'MISSING / NOT EMBEDDED'}")


if __name__ == "__main__":
    cli()
