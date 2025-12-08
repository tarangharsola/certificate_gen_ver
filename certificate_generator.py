import os
import json
import secrets
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import click


class HiddenMetadata:
    @staticmethod
    def generate_checksum(data: Dict, secret: Optional[str] = None) -> str:
        if secret is None:
            secret = os.getenv("CERT_SECRET", "default-secret")
        s = json.dumps(data, sort_keys=True)
        return hmac.new(secret.encode(), s.encode(), hashlib.sha256).hexdigest()[:16]

    @staticmethod
    def generate_token() -> Tuple[str, str]:
        token = secrets.token_urlsafe(16)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token, token_hash

    @staticmethod
    def embed_in_pdf_metadata(canvas_obj, cert_data: Dict):
        payload = {
            "id": cert_data["certificate_id"],
            "token_hash": cert_data["credentials"]["token_hash"],
            "checksum": cert_data["credentials"]["checksum"],
        }

        hidden_str = "CertGen|" + json.dumps(payload, separators=(",", ":"))

        canvas_obj.setTitle(f"Certificate {cert_data['certificate_id']}")
        canvas_obj.setAuthor(cert_data["issuer"])
        canvas_obj.setSubject(cert_data["title"])
        canvas_obj.setCreator(hidden_str)


class CertificateGenerator:
    def __init__(self):
        self.output_dir = Path("certificates")
        self.output_dir.mkdir(exist_ok=True)
        self.store_file = Path("credentials.json")
        if not self.store_file.exists():
            self.store_file.write_text("[]", encoding="utf-8")

    @staticmethod
    def generate_random_cert_id() -> str:
        return f"CERT-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(12).upper()}"

    def _save_to_local_store(self, record: Dict):
        with self.store_file.open("r+", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                data = []
            data.append(record)
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()

    def generate_certificate(self, recipient_name, issue_date, cert_id, output_name, device):

        if not output_name.endswith(".pdf"):
            output_name += ".pdf"

        output_path = self.output_dir / output_name
        page_width, page_height = landscape(A4)

        c = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))
        c.setFillColor(colors.white)
        c.rect(0, 0, page_width, page_height, fill=True)

        c.setFont("Helvetica-Bold", 40)
        c.drawCentredString(page_width / 2, page_height - 1.5 * inch, "Data Sanitization Certificate")

        c.setFont("Helvetica", 24)
        c.drawCentredString(page_width / 2, page_height - 2.3 * inch, "This is to certify that")

        c.setFont("Helvetica-Bold", 32)
        c.drawCentredString(page_width / 2, page_height - 3.3 * inch, recipient_name)

        os_name = device.get("Operating System", "Unknown OS")
        size_removed = device.get("size_removed", "N/A")
        device_id = device.get("device_id", "N/A")
        action_type = device.get("action_type")
        timestamp = device.get("timestamp", "N/A")

        action_phrase = "a secure purge operation" if action_type == "purge" else "a standard clean operation"

        text = c.beginText(2 * inch, page_height - 4.3 * inch)
        text.setFont("Helvetica", 14)
        text.setLeading(20)
        text.textLine(f"On {timestamp}, device {device_id} running {os_name}")
        text.textLine(f"underwent {action_phrase}.")
        text.textLine(f"Approximately {size_removed} of storage space was recovered.")
        c.drawText(text)

        issuer = "Device Sanitization Authority"
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * inch, 1.3 * inch, f"Issued by: {issuer}")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, 1.0 * inch, f"Certificate Number: {cert_id}")
        c.drawString(1 * inch, 0.7 * inch, f"Issue Date: {issue_date}")

        cert_data = {
            "certificate_id": cert_id,
            "recipient_name": recipient_name,
            "issue_date": issue_date,
            "issuer": issuer,
            "title": "Data Sanitization Certificate",
            "generated_at": datetime.now().isoformat(),
        }

        _, token_hash = HiddenMetadata.generate_token()
        checksum = HiddenMetadata.generate_checksum(cert_data)

        cert_data["credentials"] = {
            "token_hash": token_hash,
            "checksum": checksum,
        }

        HiddenMetadata.embed_in_pdf_metadata(c, cert_data)
        c.save()

        cert_data["file_path"] = str(output_path)
        cert_data["device_info"] = device
        cert_data["record_type"] = "certificate"
        self._save_to_local_store(cert_data)

        return output_path


@click.group()
def cli():
    pass


@cli.command()
@click.option("--input", required=True, type=click.Path(exists=True))
def create(input):

    with open(input, "r", encoding="utf-8") as f:
        data = json.load(f)

    user = data["user"]
    device = data["device"]

    if device.get("action_type") not in ("purge", "clear"):
        click.secho("✗ Invalid action_type. Only 'purge' or 'clear' allowed.", fg="red")
        return

    gen = CertificateGenerator()
    cert_id = gen.generate_random_cert_id()

    path = gen.generate_certificate(
        recipient_name=user["name"],
        issue_date=user.get("date", datetime.now().strftime("%B %d, %Y")),
        cert_id=cert_id,
        output_name=user.get("output", "certificate"),
        device=device,
    )

    click.secho("✓ Certificate generated successfully", fg="green")
    click.echo(f"  File: {path}")
    click.echo(f"  Certificate ID: {cert_id}")


if __name__ == "__main__":
    cli()
