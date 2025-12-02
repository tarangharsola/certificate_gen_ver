"""
Certificate Generator - A tool to create customizable PDF certificates
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from reportlab.lib.pagesizes import landscape, letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from PIL import Image, ImageDraw, ImageFont
import click


class CertificateGenerator:
    """Generate customized certificates in PDF format."""
    
    def __init__(self, template_config: Optional[Dict] = None):
        """
        Initialize certificate generator.
        
        Args:
            template_config: Dictionary with certificate template settings
        """
        self.template_config = template_config or self._default_template()
        self.output_dir = Path("certificates")
        self.output_dir.mkdir(exist_ok=True)
    
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
        }
    
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
    ) -> Path:
        """
        Generate a single certificate.
        
        Args:
            recipient_name: Name of the certificate recipient
            course_name: Name of the course/achievement
            issue_date: Date of issue (defaults to today)
            certificate_number: Unique certificate number
            output_filename: Output file name (defaults to recipient_name)
        
        Returns:
            Path to the generated certificate
        """
        if issue_date is None:
            issue_date = datetime.now().strftime("%B %d, %Y")
        
        if certificate_number is None:
            certificate_number = f"CERT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        if output_filename is None:
            safe_name = "".join(c for c in recipient_name if c.isalnum() or c in " _-")
            output_filename = f"{safe_name.replace(' ', '_')}.pdf"
        
        filepath = self.output_dir / output_filename
        
        page_width, page_height = self._get_page_size()
        
        # Create PDF
        c = canvas.Canvas(str(filepath), pagesize=(page_width, page_height))
        
        # Add background color
        bg_color = self.template_config.get("background_color", (255, 255, 255))
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
        
        # Add issue date and certificate number
        c.setFont("Helvetica", 12)
        c.setFillColor(colors.HexColor(hex_color))
        c.drawString(0.8 * inch, 0.8 * inch, f"Certificate #: {certificate_number}")
        c.drawRightString(page_width - 0.8 * inch, 0.8 * inch, f"Date: {issue_date}")
        
        # Add issuer
        issuer = self.template_config.get("issuer", "Certificate Authority")
        c.setFont("Helvetica-Bold", 14)
        c.drawString(0.8 * inch, 1.2 * inch, f"Issued by: {issuer}")
        
        c.save()
        return filepath
    
    def generate_batch(self, recipients: List[Dict]) -> List[Path]:
        """
        Generate certificates for multiple recipients.
        
        Args:
            recipients: List of dictionaries with recipient information
                       Required keys: 'name', 'course'
                       Optional keys: 'date', 'certificate_number', 'output_filename'
        
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
            )
            generated_certificates.append(path)
        
        return generated_certificates
    
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
    """Certificate Generator CLI"""
    pass


@cli.command()
@click.option('--name', prompt='Recipient name', help='Name of the certificate recipient')
@click.option('--course', prompt='Course name', help='Name of the course/achievement')
@click.option('--date', default=None, help='Issue date (defaults to today)')
@click.option('--number', default=None, help='Certificate number')
@click.option('--output', default=None, help='Output filename')
def create(name: str, course: str, date: Optional[str], number: Optional[str], output: Optional[str]):
    """Create a single certificate"""
    generator = CertificateGenerator()
    filepath = generator.generate_certificate(
        recipient_name=name,
        course_name=course,
        issue_date=date,
        certificate_number=number,
        output_filename=output,
    )
    click.echo(f"✓ Certificate created: {filepath}")


@cli.command()
@click.option('--input', required=True, type=click.Path(exists=True), 
              help='JSON file with recipient data')
@click.option('--template', default=None, type=click.Path(exists=True),
              help='JSON file with template configuration')
def batch(input: str, template: Optional[str]):
    """Create certificates in batch from JSON file"""
    generator = CertificateGenerator()
    
    if template:
        generator.load_template_from_json(template)
    
    recipients = generator.load_recipients_from_json(input)
    paths = generator.generate_batch(recipients)
    
    click.echo(f"✓ Generated {len(paths)} certificates:")
    for path in paths:
        click.echo(f"  - {path}")


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
        "border_width": 3
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
            "date": "December 01, 2025",
            "certificate_number": "CERT-001"
        },
        {
            "name": "Jane Smith",
            "course": "Advanced Python Programming",
            "date": "December 01, 2025",
            "certificate_number": "CERT-002"
        }
    ]
    
    with open(output, 'w') as f:
        json.dump(sample_recipients, f, indent=2)
    
    click.echo(f"✓ Recipients file saved to: {output}")


if __name__ == '__main__':
    cli()
