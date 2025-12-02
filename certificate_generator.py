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
    def generate_checksum(data: Dict, secret: str = "default-secret") -> str:
        """Generate HMAC checksum for certificate data integrity."""
        data_str = json.dumps(data, sort_keys=True)
        return hmac.new(
            secret.encode(),
            data_str.encode(),
            hashlib.sha256
        ).hexdigest()[:16]  # first 16 chars
    
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
            hidden_str = json.dumps({
                "id": cert_data.get('certificate_id'),
                "hash": HiddenMetadata.generate_checksum(cert_data)
            }, separators=(',', ':'))
            
            # Truncate if too long
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
            "qr_size": 1.0,
            "qr_margin": 0.6,
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
        qr_size = float(self.template_config.get("qr_size", 1.0))
        qr_margin = float(self.template_config.get("qr_margin", 0.6))
        qr_position = str(self.template_config.get("qr_position", "bottom-right")).lower()

        # Only increase the bottom band when the QR is placed in a bottom position
        if qr_enabled and qr_position.startswith("bottom"):
            required_qr_height = (qr_margin + qr_size + 0.2) * inch
        else:
            required_qr_height = 0.0

        default_band = 1.0 * inch
        bottom_band_height = max(default_band, required_qr_height)

        issuer_y = bottom_band_height + 0.3 * inch
        metadata_y = bottom_band_height / 2.0

        # Draw issuer
        issuer = self.template_config.get("issuer", "Certificate Authority")
        c.setFont("Helvetica-Bold", 14)
        c.drawString(0.8 * inch, issuer_y, f"Issued by: {issuer}")

        # Add issue date and certificate number
        c.setFont("Helvetica", 12)
        c.setFillColor(colors.HexColor(hex_color))
        c.drawString(0.8 * inch, metadata_y, f"Certificate #: {certificate_number}")
        c.drawRightString(page_width - 0.8 * inch, metadata_y, f"Date: {issue_date}")

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
            except Exception:
                pass

        # Embed hidden metadata in PDF
        cert_data = {
            "certificate_id": certificate_number,
            "recipient_name": recipient_name,
            "course_name": course_name,
            "issue_date": issue_date,
            "issuer": issuer,
            "generated_at": datetime.now().isoformat(),
        }
        HiddenMetadata.embed_in_pdf_metadata(c, cert_data)

        c.save()

        # Store in MongoDB if enabled
        if store_in_db and self.mongo and self.mongo.connected:
            cert_data["created_at"] = datetime.now()
            cert_data["file_path"] = str(filepath)
            self.mongo.store_certificate(cert_data)

        return filepath
    
    def generate_batch(self, recipients: List[Dict], store_in_db: bool = True) -> List[Path]:
        """
        Generate certificates for multiple recipients.
        
        Args:
            recipients: List of dictionaries with recipient information
            store_in_db: Whether to store in MongoDB
        
        Returns:
            List of paths to generated certificates
        """
        generated_certificates = []
        for recipient in recipients:
            path = self.generate_certificate(
                recipient_name=recipient["name"],
                course_name=recipient["course"],
                issue_date=recipient.get("date"),
                certificate_number=recipient.get("certificate_number"),
                output_filename=recipient.get("output_filename"),
                store_in_db=store_in_db,
            )
            generated_certificates.append(path)
        
        return generated_certificates
    
    def verify_certificate(self, certificate_id: str, recipient_name: str, course_name: str) -> Dict:
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
        
        return {
            "verified": True,
            "certificate_id": certificate_id,
            "recipient_name": recipient_name,
            "course_name": course_name,
            "issue_date": record.get("issue_date"),
            "issuer": record.get("issuer"),
            "generated_at": record.get("generated_at"),
        }
    
    @staticmethod
    def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
        """Convert RGB tuple to hex color string."""
        return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])
    
    def load_recipients_from_json(self, filepath: str) -> List[Dict]:
        """Load recipient data from JSON file."""
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def load_template_from_json(self, filepath: str):
        """Load template configuration from JSON file."""
        with open(filepath, 'r') as f:
            self.template_config = json.load(f)


# CLI Commands
@click.group()
def cli():
    """Certificate Generator CLI with hidden metadata and MongoDB tracking"""
    pass


@cli.command()
@click.option('--name', prompt='Recipient name', help='Name of the certificate recipient')
@click.option('--course', prompt='Course name', help='Name of the course/achievement')
@click.option('--date', default=None, help='Issue date (defaults to today)')
@click.option('--output', default=None, help='Output filename')
@click.option('--mongo-uri', default=None, help='MongoDB URI (or use MONGODB_URI env var)')
@click.option('--store/--no-store', default=True, help='Store in MongoDB (default: true)')
def create(name: str, course: str, date: Optional[str], output: Optional[str], mongo_uri: Optional[str], store: bool):
    """Create a single certificate with random ID and optional MongoDB storage"""
    generator = CertificateGenerator(mongo_uri=mongo_uri)
    cert_id = CertificateGenerator.generate_random_cert_id()
    filepath = generator.generate_certificate(
        recipient_name=name,
        course_name=course,
        issue_date=date,
        certificate_number=cert_id,
        output_filename=output,
        store_in_db=store,
    )
    click.echo(f"✓ Certificate created: {filepath}")
    click.echo(f"  Certificate ID: {cert_id}")


@cli.command()
@click.option('--input', required=True, type=click.Path(exists=True), 
              help='JSON file with recipient data')
@click.option('--template', default=None, type=click.Path(exists=True),
              help='JSON file with template configuration')
@click.option('--mongo-uri', default=None, help='MongoDB URI')
@click.option('--store/--no-store', default=True, help='Store in MongoDB (default: true)')
def batch(input: str, template: Optional[str], mongo_uri: Optional[str], store: bool):
    """Create certificates in batch from JSON file"""
    generator = CertificateGenerator(mongo_uri=mongo_uri)
    
    if template:
        generator.load_template_from_json(template)
    
    recipients = generator.load_recipients_from_json(input)
    paths = generator.generate_batch(recipients, store_in_db=store)
    
    click.echo(f"✓ Generated {len(paths)} certificates:")
    for path in paths:
        click.echo(f"  - {path}")


@cli.command()
@click.option('--cert-id', prompt='Certificate ID', help='Certificate ID to verify')
@click.option('--name', prompt='Recipient name', help='Recipient name')
@click.option('--course', prompt='Course name', help='Course name')
@click.option('--mongo-uri', default=None, help='MongoDB URI')
def verify(cert_id: str, name: str, course: str, mongo_uri: Optional[str]):
    """Verify a certificate against MongoDB records"""
    generator = CertificateGenerator(mongo_uri=mongo_uri)
    
    result = generator.verify_certificate(cert_id, name, course)
    
    if result["verified"]:
        click.secho("✓ Certificate VERIFIED", fg="green")
        click.echo(f"  ID: {result['certificate_id']}")
        click.echo(f"  Recipient: {result['recipient_name']}")
        click.echo(f"  Course: {result['course_name']}")
        click.echo(f"  Issued: {result['issue_date']}")
        click.echo(f"  Issuer: {result['issuer']}")
    else:
        click.secho(f"✗ Certificate INVALID: {result['reason']}", fg="red")


@cli.command()
@click.option('--output', default='template.json', help='Output template filename')
def template(output: str):
    """Generate a sample template configuration file"""
    sample_template = {
        "page_size": "landscape",
        "title": "Certificate of Achievement",
        "subtitle": "This is to certify that",
        "issuer": "Your Organization",
        "background_color": [255, 255, 255],
        "text_color": [0, 0, 0],
        "accent_color": [70, 130, 180],
        "border": True,
        "border_width": 3,
        "qr": True,
        "qr_size": 1.0,
        "qr_margin": 0.6,
        "qr_position": "bottom-right",
        "base_url": "https://example.com/verify"
    }
    
    with open(output, 'w') as f:
        json.dump(sample_template, f, indent=2)
    
    click.echo(f"✓ Template saved to: {output}")


@cli.command()
@click.option('--output', default='recipients.json', help='Output recipients filename')
def recipients(output: str):
    """Generate a sample recipients data file"""
    sample_recipients = [
        {
            "name": "John Doe",
            "course": "Advanced Python Programming",
            "date": "December 01, 2025"
        },
        {
            "name": "Jane Smith",
            "course": "Advanced Python Programming",
            "date": "December 01, 2025"
        }
    ]
    
    with open(output, 'w') as f:
        json.dump(sample_recipients, f, indent=2)
    
    click.echo(f"✓ Recipients file saved to: {output}")


if __name__ == '__main__':
    cli()
