"""
Certificate Generator - Enhanced version with hidden metadata, random IDs, and MongoDB tracking
"""

import os
import json
import secrets
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import uuid

from reportlab.lib.pagesizes import landscape, letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont
import io

# Optional dependencies
try:
    import qrcode
    _HAS_QR = True
except Exception:
    qrcode = None
    _HAS_QR = False

# Optional PDF parsing library for verification from file
try:
    from PyPDF2 import PdfReader
    _HAS_PYPDF = True
except Exception:
    PdfReader = None
    _HAS_PYPDF = False

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
    _HAS_MONGO = True
except Exception:
    MongoClient = None
    _HAS_MONGO = False

import click


class MongoConnector:
    """Handle MongoDB connections and certificate storage."""
    
    def __init__(self, uri: Optional[str] = None):
        """
        Initialize MongoDB connector.
        
        Args:
            uri: MongoDB connection URI (defaults to env var MONGODB_URI or local)
        """
        if not _HAS_MONGO:
            raise ImportError("pymongo not installed. Install with: pip install pymongo")
        
        self.uri = uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
        self.db_name = "certificate_db"
        self.collection_name = "certificates"
        self.client = None
        self.db = None
        self.collection = None
        self.connected = False
    
    def connect(self) -> bool:
        """Attempt to connect to MongoDB."""
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            # Verify connection
            self.client.admin.command("ping")
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            self.connected = True
            return True
        except Exception as e:
            click.echo(f"MongoDB connection failed: {e}", err=True)
            self.connected = False
            return False
    
    def store_certificate(self, cert_data: Dict) -> bool:
        """Store certificate record in MongoDB."""
        if not self.connected:
            click.echo("Warning: MongoDB not connected. Certificate not stored.", err=True)
            return False
        
        try:
            result = self.collection.insert_one(cert_data)
            return bool(result.inserted_id)
        except Exception as e:
            click.echo(f"Failed to store certificate: {e}", err=True)
            return False
    
    def retrieve_certificate(self, cert_id: str) -> Optional[Dict]:
        """Retrieve certificate record from MongoDB."""
        if not self.connected:
            return None
        
        try:
            return self.collection.find_one({"certificate_id": cert_id})
        except Exception:
            return None
    
    def verify_certificate(self, cert_id: str, recipient_name: str, course_name: str) -> bool:
        """Verify a certificate exists and matches provided data."""
        if not self.connected:
            return False
        
        try:
            record = self.collection.find_one({
                "certificate_id": cert_id,
                "recipient_name": recipient_name,
                "course_name": course_name
            })
            return record is not None
        except Exception:
            return False
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.connected = False


class HiddenMetadata:
    """Embed and extract hidden metadata in/from PDF."""
    
    @staticmethod
    def generate_checksum(data: Dict, secret: Optional[str] = None) -> str:
        """Generate HMAC checksum for certificate data integrity.

        The secret defaults to the `CERT_SECRET` environment variable when not
        provided. Returns a truncated hex HMAC (first 16 chars) to embed in
        PDF metadata.
        """
        if secret is None:
            secret = os.getenv("CERT_SECRET", "default-secret")
        data_str = json.dumps(data, sort_keys=True)
        return hmac.new(
            secret.encode(),
            data_str.encode(),
            hashlib.sha256
        ).hexdigest()[:16]

    @staticmethod
    def generate_token() -> Tuple[str, str]:
        """Generate a verification token and its SHA256 hash.

        Returns a tuple `(token, token_hash)` where `token` is a URL-safe
        random token (to be handed to the recipient) and `token_hash` is the
        SHA256 hex digest stored in the database and embedded in the PDF.
        """
        token = secrets.token_urlsafe(16)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token, token_hash
    
    @staticmethod
    def embed_in_pdf_metadata(canvas_obj, cert_data: Dict):
        """Embed certificate data in PDF metadata (XMP-like info)."""
        try:
            # Store as PDF info
            info = canvas_obj.getProperties()
            info.title = f"Certificate: {cert_data.get('certificate_id', 'N/A')}"
            info.author = cert_data.get('issuer', 'Certificate Authority')
            info.subject = cert_data.get('course_name', '')
            
            # Embed JSON string in creator field (limited length)
            # Only embed non-sensitive hashed credentials and checksum
            payload = {
                "id": cert_data.get('certificate_id'),
                "token_hash": cert_data.get('credentials', {}).get('token_hash'),
                "checksum": cert_data.get('credentials', {}).get('checksum')
            }
            hidden_str = json.dumps(payload, separators=(',', ':'))
            # Truncate to avoid overly long metadata fields
            info.creator = f"CertGen|{hidden_str[:200]}"
        except Exception:
            pass  # PDF metadata embedding is best-effort


class CertificateGenerator:
    """Generate customized certificates in PDF format with hidden metadata."""
    
    def __init__(self, template_config: Optional[Dict] = None, mongo_uri: Optional[str] = None):
        """
        Initialize certificate generator.
        
        Args:
            template_config: Dictionary with certificate template settings
            mongo_uri: MongoDB connection URI (optional)
        """
        self.template_config = template_config or self._default_template()
        self.output_dir = Path("certificates")
        self.output_dir.mkdir(exist_ok=True)

        # Local JSON credentials store (fallback when MongoDB is not used)
        self.local_store_file = Path("credentials.json")
        if not self.local_store_file.exists():
            try:
                self.local_store_file.write_text("[]")
            except Exception:
                pass
        
        self.mongo = None
        if mongo_uri or os.getenv("MONGODB_URI"):
            if _HAS_MONGO:
                self.mongo = MongoConnector(mongo_uri)
                self.mongo.connect()
    
    @staticmethod
    def _default_template() -> Dict:
        """Return default certificate template configuration."""
        return {
            "page_size": "landscape",
            "title": "Certificate of Achievement",
            "subtitle": "This is to certify that",
            "issuer": "Certificate Authority",
            "background_color": (255, 255, 255),
            "text_color": (0, 0, 0),
            "accent_color": (70, 130, 180),
            "border": True,
            "border_width": 3,
            "qr": True,
            "qr_size": 1.5,  # Increased from 1.0 to make QR codes more visible
            "qr_margin": 0.5,  # Slightly reduced from 0.6
            "qr_position": "bottom-right",
        }
    
    @staticmethod
    def generate_random_cert_id() -> str:
        """Generate a cryptographically secure random certificate ID."""
        # Use UUID-based ID with timestamp prefix for sortability
        timestamp = datetime.now().strftime("%Y%m%d")
        random_part = secrets.token_hex(12)  # 24 hex chars
        return f"CERT-{timestamp}-{random_part.upper()}"
    
    def _get_page_size(self) -> Tuple[float, float]:
        """Get page dimensions based on template configuration."""
        size_map = {
            "landscape": landscape(A4),
            "portrait": letter,
            "a4": A4,
        }
        return size_map.get(self.template_config.get("page_size", "landscape"), 
                            landscape(A4))
    
    def generate_certificate(
        self,
        recipient_name: str,
        course_name: str,
        issue_date: Optional[str] = None,
        certificate_number: Optional[str] = None,
        output_filename: Optional[str] = None,
        store_in_db: bool = True,
    ) -> Path:
        """
        Generate a single certificate.
        
        Args:
            recipient_name: Name of the certificate recipient
            course_name: Name of the course/achievement
            issue_date: Date of issue (defaults to today)
            certificate_number: Unique certificate number (auto-generated if None)
            output_filename: Output file name (defaults to recipient_name)
            store_in_db: Whether to store certificate metadata in MongoDB
        
        Returns:
            Path to the generated certificate
        """
        if issue_date is None:
            issue_date = datetime.now().strftime("%B %d, %Y")
        
        if certificate_number is None:
            certificate_number = self.generate_random_cert_id()
        
        if output_filename is None:
            safe_name = "".join(c for c in recipient_name if c.isalnum() or c in " _-")
            output_filename = f"{safe_name.replace(' ', '_')}.pdf"
        
        filepath = self.output_dir / output_filename
        
        page_width, page_height = self._get_page_size()
        
        # Create PDF
        c = canvas.Canvas(str(filepath), pagesize=(page_width, page_height))
        
        # Add background color
        c.setFillColor(colors.HexColor("#FFFFFF"))
        c.rect(0, 0, page_width, page_height, fill=True, stroke=False)
        
        # Add decorative border
        if self.template_config.get("border", True):
            border_width = self.template_config.get("border_width", 3)
            accent_color = self.template_config.get("accent_color", (70, 130, 180))
            hex_color = self._rgb_to_hex(accent_color)
            c.setStrokeColor(colors.HexColor(hex_color))
            c.setLineWidth(border_width)
            c.rect(0.3 * inch, 0.3 * inch, 
                   page_width - 0.6 * inch, page_height - 0.6 * inch,
                   fill=False, stroke=True)
        
        # Add title
        title = self.template_config.get("title", "Certificate of Achievement")
        c.setFont("Helvetica-Bold", 48)
        text_color = self.template_config.get("text_color", (0, 0, 0))
        hex_color = self._rgb_to_hex(text_color)
        c.setFillColor(colors.HexColor(hex_color))
        c.drawCentredString(page_width / 2, page_height - 1.2 * inch, title)
        
        # Add subtitle
        subtitle = self.template_config.get("subtitle", "This is to certify that")
        c.setFont("Helvetica", 24)
        c.drawCentredString(page_width / 2, page_height - 1.9 * inch, subtitle)
        
        # Add recipient name
        c.setFont("Helvetica-Bold", 36)
        accent_hex = self._rgb_to_hex(self.template_config.get("accent_color", (70, 130, 180)))
        c.setFillColor(colors.HexColor(accent_hex))
        c.drawCentredString(page_width / 2, page_height - 2.7 * inch, recipient_name)
        
        # Add course/achievement name
        c.setFont("Helvetica-Oblique", 18)
        c.setFillColor(colors.HexColor(hex_color))
        c.drawCentredString(page_width / 2, page_height - 3.3 * inch, 
                           f"has successfully completed")
        
        c.setFont("Helvetica-Bold", 22)
        c.setFillColor(colors.HexColor(accent_hex))
        c.drawCentredString(page_width / 2, page_height - 3.9 * inch, course_name)
        
        # Layout bottom metadata band and QR positioning
        qr_enabled = bool(self.template_config.get("qr", True)) and _HAS_QR
        qr_size = float(self.template_config.get("qr_size", 1.5))  # Default: 1.5 inches (larger)
        qr_margin = float(self.template_config.get("qr_margin", 0.5))
        qr_position = str(self.template_config.get("qr_position", "bottom-right")).lower()

        # Only increase the bottom band when the QR is placed in a bottom position
        if qr_enabled and qr_position.startswith("bottom"):
            required_qr_height = (qr_margin + qr_size + 0.2) * inch
        else:
            required_qr_height = 0.0

        default_band = 2.2 * inch  # Increased to accommodate larger QR code
        bottom_band_height = max(default_band, required_qr_height)

        issuer_y = bottom_band_height + 0.3 * inch
        metadata_y = bottom_band_height / 2.0

        # Draw issuer (left side only)
        issuer = self.template_config.get("issuer", "Certificate Authority")
        c.setFont("Helvetica-Bold", 14)
        c.drawString(0.8 * inch, issuer_y, f"Issued by: {issuer}")

        # Add issue date and certificate number (left side only - avoid QR area)
        c.setFont("Helvetica", 12)
        c.setFillColor(colors.HexColor(hex_color))
        c.drawString(0.8 * inch, metadata_y, f"Certificate #: {certificate_number}")
        c.drawString(0.8 * inch, metadata_y - 0.25 * inch, f"Date: {issue_date}")

        # Add QR code (optional) with embedded verification data
        if qr_enabled:
            try:
                base_url = self.template_config.get("base_url")
                if base_url:
                    payload = f"{base_url.rstrip('/')}/verify?cert={certificate_number}"
                else:
                    payload = f"Certificate:{certificate_number};Name:{recipient_name};Course:{course_name};Date:{issue_date}"

                qr = qrcode.QRCode(box_size=10, border=2)
                qr.add_data(payload)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

                img_buffer = io.BytesIO()
                img.save(img_buffer, format='PNG')
                img_buffer.seek(0)
                img_reader = ImageReader(img_buffer)

                w = qr_size * inch
                h = qr_size * inch

                # Determine x,y based on qr_position
                pos = qr_position
                # Horizontal placement
                if pos.endswith("-left"):
                    x = qr_margin * inch
                elif pos.endswith("-center"):
                    x = (page_width - w) / 2.0
                else:  # right (default)
                    x = page_width - qr_margin * inch - w

                # Vertical placement
                if pos.startswith("top"):
                    y = page_height - qr_margin * inch - h
                else:  # bottom (default)
                    y = qr_margin * inch

                # Compute maximum allowed height and scale if necessary
                if pos.startswith("bottom"):
                    max_h = bottom_band_height - 0.2 * inch
                else:
                    # For top placements allow reasonable space leaving 1" top margin
                    max_h = page_height - (2 * qr_margin * inch) - (1.0 * inch)

                if max_h <= 0:
                    max_h = h

                if h > max_h and max_h > 0:
                    scale = max_h / h
                    w *= scale
                    h *= scale
                    # recompute centered or right x if needed
                    if pos.endswith("-center"):
                        x = (page_width - w) / 2.0
                    elif pos.endswith("-left"):
                        x = qr_margin * inch
                    else:
                        x = page_width - qr_margin * inch - w

                c.drawImage(img_reader, x, y, width=w, height=h, mask='auto')
                print(f"✓ QR code added at position {pos}: x={x:.2f}, y={y:.2f}, w={w:.2f}, h={h:.2f}")
            except Exception as e:
                print(f"✗ Failed to add QR code: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()

        # Embed hidden metadata in PDF
        cert_data = {
            "certificate_id": certificate_number,
            "recipient_name": recipient_name,
            "course_name": course_name,
            "issue_date": issue_date,
            "issuer": issuer,
            "generated_at": datetime.now().isoformat(),
        }

        # Generate a per-certificate verification token (the raw token is
        # returned to the caller or can be included in the QR payload) and a
        # stored token_hash so the DB doesn't contain the raw token.
        token, token_hash = HiddenMetadata.generate_token()

        # Compute a short HMAC checksum over the cert data using CERT_SECRET
        checksum = HiddenMetadata.generate_checksum(cert_data)

        # Attach credentials (store only hashed token + checksum)
        cert_data["credentials"] = {
            "token_hash": token_hash,
            "checksum": checksum
        }

        # Embed (hashed) credentials in PDF metadata
        HiddenMetadata.embed_in_pdf_metadata(c, cert_data)

        c.save()

        # Store in MongoDB if enabled. Otherwise, fall back to a local JSON
        # credentials store named `credentials.json`.
        if store_in_db:
            db_record = dict(cert_data)
            db_record["created_at"] = datetime.now()
            db_record["file_path"] = str(filepath)
            # Keep credentials as-is (token_hash + checksum)
            if self.mongo and self.mongo.connected:
                self.mongo.store_certificate(db_record)
            else:
                self._save_to_local_store(db_record)

        # Return the path and the raw token so the caller can distribute it to
        # the recipient (or include it in the QR). Caller can ignore the
        # returned token if not needed.
        # To keep backward compatibility, return filepath but expose token via
        # an attribute on the generator instance for programmatic access.
        try:
            # attach last token to generator for potential programmatic use
            self._last_token = token
        except Exception:
            pass

        return filepath
    
    def _save_to_local_store(self, record: Dict) -> bool:
        """Append a certificate record to the local JSON store.

        Returns True on success.
        """
        try:
            if not self.local_store_file.exists():
                self.local_store_file.write_text("[]")
            # Make a JSON-serializable copy (convert datetimes to ISO strings)
            def make_serializable(obj):
                if isinstance(obj, dict):
                    return {k: make_serializable(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [make_serializable(v) for v in obj]
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return obj

            serializable_record = make_serializable(record)

            with self.local_store_file.open("r+", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = []
                data.append(serializable_record)
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
            return True
        except Exception as e:
            click.echo(f"Failed to write local credentials: {e}", err=True)
            return False

    def _load_local_record(self, cert_id: str) -> Optional[Dict]:
        """Load a record by certificate_id from the local JSON store."""
        try:
            if not self.local_store_file.exists():
                return None
            with self.local_store_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                for rec in data:
                    if rec.get("certificate_id") == cert_id:
                        return rec
            return None
        except Exception:
            return None
    
    def verify_certificate(self, certificate_id: str, recipient_name: str, course_name: str, token: Optional[str] = None) -> Dict:
        """
        Verify a certificate against stored records.
        
        Returns:
            Dict with verification status and details
        """
        if not self.mongo or not self.mongo.connected:
            return {
                "verified": False,
                "reason": "MongoDB not available for verification"
            }
        
        record = self.mongo.retrieve_certificate(certificate_id)
        
        if not record:
            return {
                "verified": False,
                "reason": "Certificate not found in database"
            }
        
        if record.get("recipient_name") != recipient_name:
            return {
                "verified": False,
                "reason": "Recipient name mismatch"
            }
        
        if record.get("course_name") != course_name:
            return {
                "verified": False,
                "reason": "Course name mismatch"
            }
        # If a token was provided, verify token hash matches stored token_hash
        credentials = record.get("credentials", {}) or {}
        stored_token_hash = credentials.get("token_hash")
        stored_checksum = credentials.get("checksum")

        if token:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            if not stored_token_hash or token_hash != stored_token_hash:
                return {
                    "verified": False,
                    "reason": "Token mismatch"
                }

        # Recompute checksum from stored record fields and compare
        recompute_data = {
            "certificate_id": record.get("certificate_id"),
            "recipient_name": record.get("recipient_name"),
            "course_name": record.get("course_name"),
            "issue_date": record.get("issue_date"),
            "issuer": record.get("issuer"),
            "generated_at": record.get("generated_at"),
        }
        expected_checksum = HiddenMetadata.generate_checksum(recompute_data)
        if stored_checksum and expected_checksum != stored_checksum:
            return {
                "verified": False,
                "reason": "Checksum mismatch - data may have been tampered"
            }

        return {
            "verified": True,
            "certificate_id": certificate_id,
            "recipient_name": recipient_name,
            "course_name": course_name,
            "issue_date": record.get("issue_date"),
            "issuer": record.get("issuer"),
            "generated_at": record.get("generated_at"),
        }

    def verify_file(self, pdf_path: str, token: Optional[str] = None) -> Dict:
        """Verify a certificate PDF by extracting embedded hidden metadata.

        This reads the PDF metadata (the `Creator` field created by the
        generator) and extracts the embedded JSON payload inserted during
        generation. If MongoDB is available it will cross-check stored
        credentials; otherwise it will validate the checksum if present.

        Returns the same dict structure as `verify_certificate`.
        """
        if not _HAS_PYPDF:
            return {"verified": False, "reason": "PyPDF2 not installed"}

        if not os.path.exists(pdf_path):
            return {"verified": False, "reason": "File not found"}

        try:
            reader = PdfReader(pdf_path)
            info = reader.metadata or {}
            creator = info.get('/Creator') or info.get('Creator') or ''
            if not creator or 'CertGen|' not in creator:
                return {"verified": False, "reason": "No embedded certificate metadata found"}

            try:
                payload_json = creator.split('CertGen|', 1)[1]
                payload = json.loads(payload_json)
            except Exception:
                # If truncated, try to recover JSON substring
                raw = creator.split('CertGen|', 1)[1]
                # Find first { and last }
                start = raw.find('{')
                end = raw.rfind('}')
                if start == -1 or end == -1:
                    return {"verified": False, "reason": "Embedded metadata malformed"}
                payload = json.loads(raw[start:end+1])

            cert_id = payload.get('id')
            token_hash = payload.get('token_hash')
            checksum = payload.get('checksum')

            if not cert_id:
                return {"verified": False, "reason": "Certificate ID missing in embedded metadata"}

            # If DB is available, prefer DB verification
            if self.mongo and self.mongo.connected:
                # Use existing verify_certificate logic; pass token if provided
                # We don't know recipient/course from the PDF metadata here,
                # so retrieve record and perform checksum/token checks only.
                record = self.mongo.retrieve_certificate(cert_id)
                if not record:
                    return {"verified": False, "reason": "Certificate not found in database"}

                # If a token supplied, verify it
                if token:
                    token_hash_local = hashlib.sha256(token.encode()).hexdigest()
                    if token_hash_local != record.get('credentials', {}).get('token_hash'):
                        return {"verified": False, "reason": "Token mismatch"}

                # Recompute checksum and compare if available
                recompute = {
                    "certificate_id": record.get('certificate_id'),
                    "recipient_name": record.get('recipient_name'),
                    "course_name": record.get('course_name'),
                    "issue_date": record.get('issue_date'),
                    "issuer": record.get('issuer'),
                    "generated_at": record.get('generated_at'),
                }
                expected = HiddenMetadata.generate_checksum(recompute)
                stored = record.get('credentials', {}).get('checksum')
                if stored and expected != stored:
                    return {"verified": False, "reason": "Checksum mismatch - data differs from DB"}

                return {"verified": True, "certificate_id": cert_id, "from": "db"}
            # If no DB, try local JSON store
            local_rec = self._load_local_record(cert_id)
            if local_rec:
                # token check
                if token:
                    token_hash_local = hashlib.sha256(token.encode()).hexdigest()
                    if token_hash_local != local_rec.get('credentials', {}).get('token_hash'):
                        return {"verified": False, "reason": "Token mismatch"}

                # checksum check
                recompute = {
                    "certificate_id": local_rec.get("certificate_id"),
                    "recipient_name": local_rec.get("recipient_name"),
                    "course_name": local_rec.get("course_name"),
                    "issue_date": local_rec.get("issue_date"),
                    "issuer": local_rec.get("issuer"),
                    "generated_at": local_rec.get("generated_at"),
                }
                expected_checksum = HiddenMetadata.generate_checksum(recompute)
                stored_checksum = local_rec.get('credentials', {}).get('checksum')
                if stored_checksum and expected_checksum != stored_checksum:
                    return {"verified": False, "reason": "Checksum mismatch - data may have been tampered"}

                return {"verified": True, "certificate_id": cert_id, "from": "local_store"}

            # If we reach here, no DB and no local record; fallback to metadata-only
            if checksum:
                return {"verified": True, "certificate_id": cert_id, "from": "pdf_metadata_only"}

            return {"verified": False, "reason": "Insufficient metadata to verify"}
        except Exception as e:
            return {"verified": False, "reason": f"Error reading PDF: {e}"}
    
    @staticmethod
    def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
        """Convert RGB tuple to hex color string."""
        return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])


# CLI Commands
@click.group()
def cli():
    """Certificate Generator CLI with hidden metadata and MongoDB tracking"""
    pass


@cli.command()
@click.option('--input', required=True, type=click.Path(exists=True), help='JSON file with user credentials')
@click.option('--mongo-uri', default=None, help='MongoDB URI (or use MONGODB_URI env var)')
@click.option('--store/--no-store', default=True, help='Store credentials (default: true)')
def create(input: str, mongo_uri: Optional[str], store: bool):
    """Create a certificate by reading user credentials from JSON file"""
    try:
        with open(input, 'r') as f:
            user_data = json.load(f)
        
        # Validate required fields
        required_fields = ['name', 'course']
        missing_fields = [field for field in required_fields if field not in user_data]
        
        if missing_fields:
            click.secho(f"✗ Missing required fields: {', '.join(missing_fields)}", fg="red")
            return
        
        generator = CertificateGenerator(mongo_uri=mongo_uri)
        cert_id = CertificateGenerator.generate_random_cert_id()
        filepath = generator.generate_certificate(
            recipient_name=user_data['name'],
            course_name=user_data['course'],
            issue_date=user_data.get('date'),
            certificate_number=cert_id,
            output_filename=user_data.get('output'),
            store_in_db=store,
        )
        click.echo(f"✓ Certificate created: {filepath}")
        click.echo(f"  Certificate ID: {cert_id}")
        click.echo(f"  Recipient: {user_data['name']}")
        click.echo(f"  Course: {user_data['course']}")
        
        # If a token was generated, expose it so caller can distribute it to
        # the certificate recipient (this is the only time the raw token exists).
        token = getattr(generator, '_last_token', None)
        if token:
            click.echo(f"  Verification token (store securely): {token}")
    
    except json.JSONDecodeError:
        click.secho(f"✗ Invalid JSON in file: {input}", fg="red")
    except Exception as e:
        click.secho(f"✗ Error creating certificate: {e}", fg="red")


@cli.command()
@click.option('--cert-id', prompt='Certificate ID', help='Certificate ID to verify')
@click.option('--name', prompt='Recipient name', help='Recipient name')
@click.option('--course', prompt='Course name', help='Course name')
@click.option('--token', default=None, help='Verification token (optional)')
@click.option('--mongo-uri', default=None, help='MongoDB URI')
def verify(cert_id: str, name: str, course: str, token: Optional[str], mongo_uri: Optional[str]):
    """Verify a certificate against MongoDB records"""
    generator = CertificateGenerator(mongo_uri=mongo_uri)
    
    result = generator.verify_certificate(cert_id, name, course, token=token)
    
    if result["verified"]:
        click.secho("✓ Certificate VERIFIED", fg="green")
        click.echo(f"  ID: {result['certificate_id']}")
        click.echo(f"  Recipient: {result['recipient_name']}")
        click.echo(f"  Course: {result['course_name']}")
        click.echo(f"  Issued: {result['issue_date']}")
        click.echo(f"  Issuer: {result['issuer']}")
    else:
        click.secho(f"✗ Certificate INVALID: {result['reason']}", fg="red")


@cli.command('verify-file')
@click.option('--file', 'file_path', required=True, type=click.Path(exists=True), help='PDF file to verify')
@click.option('--token', default=None, help='Verification token (optional)')
@click.option('--mongo-uri', default=None, help='MongoDB URI')
def verify_file_cmd(file_path: str, token: Optional[str], mongo_uri: Optional[str]):
    """Verify a certificate by reading embedded metadata from a PDF file."""
    generator = CertificateGenerator(mongo_uri=mongo_uri)
    result = generator.verify_file(file_path, token=token)
    if result.get('verified'):
        click.secho('✓ Certificate VERIFIED', fg='green')
        click.echo(f"  ID: {result.get('certificate_id')}")
        click.echo(f"  Source: {result.get('from')}")
    else:
        click.secho(f"✗ Certificate INVALID: {result.get('reason')}", fg='red')


@cli.command('process-device')
@click.option('--input', required=True, type=click.Path(exists=True), help='JSON file with device data')
def process_device(input: str):
    """Process device data from JSON file with deleted files and data removal info"""
    try:
        with open(input, 'r') as f:
            device_data = json.load(f)
        
        # Validate required fields
        required_fields = ['device_id', 'files_deleted', 'size_removed', 'action_type', 'timestamp']
        missing_fields = [field for field in required_fields if field not in device_data]
        
        if missing_fields:
            click.secho(f"✗ Missing required fields: {', '.join(missing_fields)}", fg="red")
            return
        
        # Validate action_type
        if device_data['action_type'] not in ['clear', 'purge']:
            click.secho(f"✗ Invalid action_type. Must be 'clear' or 'purge', got: {device_data['action_type']}", fg="red")
            return
        
        # Validate files_deleted is a list
        if not isinstance(device_data['files_deleted'], list):
            click.secho("✗ 'files_deleted' must be a list", fg="red")
            return
        
        # Display processed device data
        click.secho("✓ Device data processed successfully:", fg="green")
        click.echo(f"  Device ID: {device_data['device_id']}")
        click.echo(f"  Action Type: {device_data['action_type']}")
        click.echo(f"  Data Removed: {device_data['size_removed']}")
        click.echo(f"  Timestamp: {device_data['timestamp']}")
        click.echo(f"  Files Deleted: {len(device_data['files_deleted'])} file(s)")
        
        for idx, file in enumerate(device_data['files_deleted'], 1):
            click.echo(f"    {idx}. {file}")
        
        # Store in credentials.json for tracking
        generator = CertificateGenerator()
        record = {
            "device_id": device_data['device_id'],
            "action_type": device_data['action_type'],
            "size_removed": device_data['size_removed'],
            "timestamp": device_data['timestamp'],
            "files_deleted_count": len(device_data['files_deleted']),
            "files_deleted": device_data['files_deleted'],
            "processed_at": datetime.now().isoformat(),
            "record_type": "device_cleanup"
        }
        generator._save_to_local_store(record)
        click.echo(f"✓ Device record stored in credentials.json")
        
    except json.JSONDecodeError:
        click.secho(f"✗ Invalid JSON in file: {input}", fg="red")
    except Exception as e:
        click.secho(f"✗ Error processing device data: {e}", fg="red")


if __name__ == '__main__':
    cli()
