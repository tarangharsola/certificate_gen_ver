"""
Certificate Generator

Generates a PDF certificate for device sanitization using user_data.json.
- Uses visible, proper sentences that describe the cleanup.
- Embeds hidden metadata (token + checksum) inside the PDF.
- Stores a record in credentials.json for use by a separate verification script.
"""

import os
import json
import secrets
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from reportlab.lib.pagesizes import landscape, A4, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
import io

try:
    import qrcode
    _HAS_QR = True
except Exception:
    qrcode = None
    _HAS_QR = False

import click


# ========================= Hidden Metadata =========================

class HiddenMetadata:
    """Helpers for checksum and token that will be embedded into the PDF."""

    @staticmethod
    def generate_checksum(data: Dict, secret: Optional[str] = None) -> str:
        """
        Generate a short HMAC-based checksum for the certificate data.

        This checksum helps detect tampering. The secret can be set via
        CERT_SECRET environment variable, or a default is used.
        """
        if secret is None:
            secret = os.getenv("CERT_SECRET", "default-secret")
        data_str = json.dumps(data, sort_keys=True)
        digest = hmac.new(
            secret.encode(),
            data_str.encode(),
            hashlib.sha256
        ).hexdigest()
        return digest[:16]

    @staticmethod
    def generate_token() -> Tuple[str, str]:
        """
        Generate a random token and its SHA256 hash.

        The plain token can be given to the user for verification.
        Only the hash is stored in credentials.json and PDF metadata.
        """
        token = secrets.token_urlsafe(16)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token, token_hash

    @staticmethod
    def embed_in_pdf_metadata(canvas_obj, cert_data: Dict):
        """
        Embed minimal certificate data inside PDF properties.

        Only non-sensitive information is stored:
        - certificate_id
        - token_hash
        - checksum
        """
        try:
            info = canvas_obj.getProperties()
            info.title = f"Certificate: {cert_data.get('certificate_id', 'N/A')}"
            info.author = cert_data.get('issuer', 'Certificate Authority')
            info.subject = cert_data.get('title', 'Data Sanitization Certificate')

            payload = {
                "id": cert_data.get("certificate_id"),
                "token_hash": cert_data.get("credentials", {}).get("token_hash"),
                "checksum": cert_data.get("credentials", {}).get("checksum"),
            }

            hidden_str = json.dumps(payload, separators=(",", ":"))
            info.creator = f"CertGen|{hidden_str[:200]}"
        except Exception:
            # Metadata is optional; if it fails, the certificate is still valid.
            pass


# ========================= Certificate Generator =========================

class CertificateGenerator:
    """Core class that generates the sanitization certificate and tracks records."""

    def __init__(self, template_config: Optional[Dict] = None):
        self.template_config = template_config or self._default_template()
        self.output_dir = Path("certificates")
        self.output_dir.mkdir(exist_ok=True)

        self.local_store_file = Path("credentials.json")
        if not self.local_store_file.exists():
            try:
                self.local_store_file.write_text("[]", encoding="utf-8")
            except Exception:
                pass

        self._last_token: Optional[str] = None

    @staticmethod
    def _default_template() -> Dict:
        """Default look-and-feel for the certificate."""
        return {
            "page_size": "landscape",          # "landscape", "portrait", "a4"
            "title": "Data Sanitization Certificate",
            "subtitle": "This is to certify that",
            "issuer": "Device Sanitization Authority",
            "background_color": (255, 255, 255),
            "text_color": (0, 0, 0),
            "accent_color": (70, 130, 180),
            "border": True,
            "border_width": 3,
            "qr": True,
            "qr_size": 1.5,                    # in inches
            "qr_margin": 0.5,                  # in inches
            "qr_position": "bottom-right",     # top-left, top-center, top-right, bottom-left, bottom-center, bottom-right
        }

    @staticmethod
    def generate_random_cert_id() -> str:
        """Generate a random, unique certificate ID."""
        timestamp = datetime.now().strftime("%Y%m%d")
        random_part = secrets.token_hex(12).upper()
        return f"CERT-{timestamp}-{random_part}"

    def _get_page_size(self) -> Tuple[float, float]:
        """Return page dimensions based on template."""
        size_key = self.template_config.get("page_size", "landscape").lower()
        if size_key == "portrait":
            return letter
        if size_key == "a4":
            return A4
        return landscape(A4)

    @staticmethod
    def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])

    # ---------- Local storage helper ----------

    def _save_to_local_store(self, record: Dict) -> bool:
        """
        Append the given record to credentials.json.

        This file can later be read by a separate verification program.
        """
        try:
            if not self.local_store_file.exists():
                self.local_store_file.write_text("[]", encoding="utf-8")

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

    # ---------- Core PDF creation ----------

    def generate_certificate(
        self,
        recipient_name: str,
        issue_date: Optional[str],
        certificate_number: str,
        output_filename: str,
        device_info: Dict,
    ) -> Path:
        """
        Generate the PDF certificate using recipient and device information.

        The device_info dictionary is expected to come from the "device" field
        in user_data.json.
        """
        if issue_date is None:
            issue_date = datetime.now().strftime("%B %d, %Y")

        if not output_filename.lower().endswith(".pdf"):
            output_filename += ".pdf"

        output_path = self.output_dir / output_filename
        page_width, page_height = self._get_page_size()

        c = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))

        # Background
        c.setFillColor(colors.HexColor("#FFFFFF"))
        c.rect(0, 0, page_width, page_height, fill=True, stroke=False)

        # Border
        if self.template_config.get("border", True):
            border_width = self.template_config.get("border_width", 3)
            accent_color = self.template_config.get("accent_color", (70, 130, 180))
            c.setStrokeColor(colors.HexColor(self._rgb_to_hex(accent_color)))
            c.setLineWidth(border_width)
            c.rect(
                0.3 * inch,
                0.3 * inch,
                page_width - 0.6 * inch,
                page_height - 0.6 * inch,
                fill=False,
                stroke=True,
            )

        # Title
        title = self.template_config.get("title", "Data Sanitization Certificate")
        c.setFont("Helvetica-Bold", 48)
        text_color = self.template_config.get("text_color", (0, 0, 0))
        c.setFillColor(colors.HexColor(self._rgb_to_hex(text_color)))
        c.drawCentredString(page_width / 2, page_height - 1.2 * inch, title)

        # Subtitle
        subtitle = self.template_config.get("subtitle", "This is to certify that")
        c.setFont("Helvetica", 24)
        c.drawCentredString(page_width / 2, page_height - 1.9 * inch, subtitle)

        # Recipient name
        c.setFont("Helvetica-Bold", 36)
        accent_color = self.template_config.get("accent_color", (70, 130, 180))
        c.setFillColor(colors.HexColor(self._rgb_to_hex(accent_color)))
        c.drawCentredString(page_width / 2, page_height - 2.7 * inch, recipient_name)

        # -------- Visible device info in proper sentences (PROPERLY ALIGNED) --------

        left_margin = 1.8 * inch
        right_margin = page_width - 1.8 * inch
        text_width = right_margin - left_margin

        os_name = (
            device_info.get("Operating System")
            or device_info.get("os")
            or "the specified operating system"
        )

        device_id = device_info.get("device_id", "the specified device")

        size_removed = (
            device_info.get("size_removed")
            or device_info.get("data_recovered")
            or "the specified amount of space"
        )

        action_type_raw = (device_info.get("action_type") or "").lower()
        if action_type_raw == "purge":
            action_phrase = "a secure purge operation"
        elif action_type_raw == "clear":
            action_phrase = "a standard clean operation"
        else:
            action_phrase = "a data cleaning operation"

        timestamp_raw = device_info.get("timestamp") or ""
        if timestamp_raw:
            time_phrase = f"on {timestamp_raw}"
        else:
            time_phrase = "during the sanitization process"

        c.setFillColor(colors.HexColor(self._rgb_to_hex(text_color)))
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(page_width / 2, page_height - 3.6 * inch, "Device Sanitization Details")

        c.setFont("Helvetica", 14)

        text_object = c.beginText()
        text_object.setTextOrigin(left_margin, page_height - 4.3 * inch)
        text_object.setLeading(20)

        paragraph_1 = (
            f"This certificate confirms that {time_phrase}, device {device_id} "
            f"running {os_name} underwent {action_phrase}."
        )

        paragraph_2 = (
            f"During this process, approximately {size_removed} of storage space "
            f"was recovered from the device."
        )

        def wrap_text(text: str, max_width: float, canvas_obj) -> list:
            words = text.split()
            lines = []
            current = ""

            for word in words:
                test_line = current + (" " if current else "") + word
                if canvas_obj.stringWidth(test_line, "Helvetica", 14) <= max_width:
                    current = test_line
                else:
                    if current:
                        lines.append(current)
                    current = word

            if current:
                lines.append(current)

            return lines

        for line in wrap_text(paragraph_1, text_width, c):
            text_object.textLine(line)

        text_object.textLine("")

        for line in wrap_text(paragraph_2, text_width, c):
            text_object.textLine(line)

        c.drawText(text_object)

        # -------- Footer + QR code --------

         # -------- Footer + QR code (simplified, QR bottom-right) --------

        qr_enabled = bool(self.template_config.get("qr", True)) and _HAS_QR
        qr_size = float(self.template_config.get("qr_size", 1.5))
        qr_margin = float(self.template_config.get("qr_margin", 0.5))

        default_band = 2.2 * inch
        bottom_band_height = default_band

        issuer_y = bottom_band_height + 0.3 * inch
        metadata_y = bottom_band_height / 2.0

        issuer = self.template_config.get("issuer", "Device Sanitization Authority")
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(colors.HexColor(self._rgb_to_hex(text_color)))
        c.drawString(0.8 * inch, issuer_y, f"Issued by: {issuer}")

        c.setFont("Helvetica", 12)
        c.drawString(0.8 * inch, metadata_y, f"Certificate Number: {certificate_number}")
        c.drawString(0.8 * inch, metadata_y - 0.25 * inch, f"Issue Date: {issue_date}")

        if not _HAS_QR:
            # Library not installed; QR will not be drawn
            print("QR code not generated: 'qrcode' library is not installed.")
        elif qr_enabled:
            try:
                payload = (
                    f"Certificate:{certificate_number};"
                    f"Name:{recipient_name};"
                    f"Date:{issue_date}"
                )

                qr = qrcode.QRCode(box_size=10, border=2)
                qr.add_data(payload)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

                img_buffer = io.BytesIO()
                img.save(img_buffer, format="PNG")
                img_buffer.seek(0)
                img_reader = ImageReader(img_buffer)

                w = qr_size * inch
                h = qr_size * inch

                # Place QR clearly at bottom-right
                x = page_width - qr_margin * inch - w
                y = qr_margin * inch

                c.drawImage(img_reader, x, y, width=w, height=h, mask="auto")
            except Exception as e:
                print(f"Failed to add QR code: {type(e).__name__}: {e}")


        # -------- Hidden metadata + local record --------

        cert_data = {
            "certificate_id": certificate_number,
            "recipient_name": recipient_name,
            "issue_date": issue_date,
            "issuer": issuer,
            "title": title,
            "generated_at": datetime.now().isoformat(),
        }

        token, token_hash = HiddenMetadata.generate_token()
        checksum = HiddenMetadata.generate_checksum(cert_data)

        cert_data["credentials"] = {
            "token_hash": token_hash,
            "checksum": checksum,
        }

        HiddenMetadata.embed_in_pdf_metadata(c, cert_data)

        c.save()

        record = dict(cert_data)
        record["file_path"] = str(output_path)
        record["device_info"] = device_info
        record["record_type"] = "certificate"
        self._save_to_local_store(record)

        self._last_token = token
        return output_path

    @property
    def last_token(self) -> Optional[str]:
        """Return the most recent verification token generated."""
        return self._last_token


# ========================= CLI Commands =========================

@click.group()
def cli():
    """Certificate Generator CLI (no MongoDB, no verification here)."""
    pass


@cli.command()
@click.option("--input", required=True, type=click.Path(exists=True),
              help="JSON file with 'user' and 'device' sections")
def create(input: str):
    """
    Create a data sanitization certificate from user_data.json.

    The JSON must contain:
    - user.name
    - user.date      (optional, for printing)
    - user.output    (PDF file name without extension)
    - device.device_id
    - device.Operating System
    - device.size_removed
    - device.action_type   (must be 'purge' or 'clear' or certificate is NOT generated)
    - device.timestamp
    """
    try:
        with open(input, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            click.secho("✗ Input JSON must be an object", fg="red")
            return

        user_data = data.get("user") or {}
        device_data = data.get("device") or {}

        if not user_data:
            click.secho("✗ 'user' section missing in JSON", fg="red")
            return

        if not device_data:
            click.secho("✗ 'device' section missing in JSON", fg="red")
            return

        if "name" not in user_data:
            click.secho("✗ 'user.name' is required", fg="red")
            return

        action_type = (device_data.get("action_type") or "").lower()
        if action_type not in ("purge", "clear"):
            click.secho(
                f"✗ Invalid action_type: '{device_data.get('action_type')}'. "
                f"Certificate will not be generated. Use 'purge' or 'clear'.",
                fg="red",
            )
            return

        generator = CertificateGenerator()
        cert_id = CertificateGenerator.generate_random_cert_id()

        output_name = user_data.get("output") or user_data["name"].replace(" ", "_")

        output_path = generator.generate_certificate(
            recipient_name=user_data["name"],
            issue_date=user_data.get("date"),
            certificate_number=cert_id,
            output_filename=output_name,
            device_info=device_data,
        )

        click.secho("✓ Certificate generated successfully", fg="green")
        click.echo(f"  File path        : {output_path}")
        click.echo(f"  Certificate ID   : {cert_id}")
        click.echo(f"  Recipient Name   : {user_data['name']}")

        os_name = (
            device_data.get("Operating System")
            or device_data.get("os")
            or "N/A"
        )
        click.echo("  Device details on certificate:")
        click.echo(f"    Operating System : {os_name}")
        click.echo(f"    Device ID        : {device_data.get('device_id', 'N/A')}")
        click.echo(f"    Space Recovered  : {device_data.get('size_removed', 'N/A')}")
        click.echo(f"    Operation Type   : {device_data.get('action_type', 'N/A')}")
        click.echo(f"    Time & Date      : {device_data.get('timestamp', 'N/A')}")

        token = generator.last_token
        if token:
            click.echo(f"  Verification token (store safely): {token}")

    except json.JSONDecodeError:
        click.secho(f"✗ Invalid JSON in file: {input}", fg="red")
    except Exception as e:
        click.secho(f"✗ Error creating certificate: {e}", fg="red")


@cli.command("process-device")
@click.option("--input", required=True, type=click.Path(exists=True),
              help="JSON file with device data (either flat or with 'device' key)")
def process_device(input: str):
    """
    Process device data and store a cleanup record in credentials.json.

    Works with:
    - { "device_id": "...", "Operating System": "...", ... }
    - { "user": {...}, "device": { ... } }   (your current combined JSON)
    """
    try:
        with open(input, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, dict) and "device" in raw:
            device_data = raw["device"]
        else:
            device_data = raw

        required_fields = ["device_id", "files_deleted", "size_removed", "action_type", "timestamp"]
        missing = [f for f in required_fields if f not in device_data]

        if missing:
            click.secho(f"✗ Missing required fields: {', '.join(missing)}", fg="red")
            return

        if device_data["action_type"] not in ("purge", "clear"):
            click.secho(
                f"✗ Invalid action_type: '{device_data['action_type']}'. "
                f"Use 'purge' or 'clear'. Record will not be stored.",
                fg="red",
            )
            return

        if not isinstance(device_data["files_deleted"], list):
            click.secho("✗ 'files_deleted' must be a list", fg="red")
            return

        os_name = (
            device_data.get("Operating System")
            or device_data.get("os")
            or "N/A"
        )

        click.secho("✓ Device data processed successfully", fg="green")
        click.echo(f"  Operating System : {os_name}")
        click.echo(f"  Device ID        : {device_data['device_id']}")
        click.echo(f"  Operation Type   : {device_data['action_type']}")
        click.echo(f"  Space Recovered  : {device_data['size_removed']}")
        click.echo(f"  Time & Date      : {device_data['timestamp']}")
        click.echo(f"  Files Deleted    : {len(device_data['files_deleted'])} file(s)")

        for idx, path in enumerate(device_data["files_deleted"], 1):
            click.echo(f"    {idx}. {path}")

        generator = CertificateGenerator()
        record = {
            "record_type": "device_cleanup",
            "device_id": device_data["device_id"],
            "os": os_name,
            "action_type": device_data["action_type"],
            "size_removed": device_data["size_removed"],
            "timestamp": device_data["timestamp"],
            "files_deleted_count": len(device_data["files_deleted"]),
            "files_deleted": device_data["files_deleted"],
            "processed_at": datetime.now().isoformat(),
        }
        generator._save_to_local_store(record)
        click.echo("✓ Device cleanup record stored in credentials.json")

    except json.JSONDecodeError:
        click.secho(f"✗ Invalid JSON in file: {input}", fg="red")
    except Exception as e:
        click.secho(f"✗ Error processing device data: {e}", fg="red")


if __name__ == "__main__":
    cli()
