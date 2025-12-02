"""
Quick start script to demonstrate certificate generation
"""

from certificate_generator import CertificateGenerator
from datetime import datetime


def main():
    """Run quick start examples."""
    print("=" * 60)
    print("Certificate Generator - Quick Start")
    print("=" * 60)
    
    # Initialize generator with default template
    generator = CertificateGenerator()
    
    # Example 1: Generate a single certificate
    print("\n[1] Generating single certificate...")
    filepath = generator.generate_certificate(
        recipient_name="Alice Johnson",
        course_name="Advanced Python Programming",
        issue_date="December 02, 2025",
        certificate_number="CERT-2025-100"
    )
    print(f"✓ Certificate created: {filepath}")
    
    # Example 2: Custom template
    print("\n[2] Generating certificate with custom template...")
    custom_template = {
        "page_size": "landscape",
        "title": "Certificate of Excellence",
        "subtitle": "Proudly awarded to",
        "issuer": "Tech Academy International",
        "background_color": (255, 255, 255),
        "text_color": (20, 20, 60),
        "accent_color": (255, 140, 0),  # Dark orange
        "border": True,
        "border_width": 4,
    }
    
    custom_generator = CertificateGenerator(template_config=custom_template)
    filepath = custom_generator.generate_certificate(
        recipient_name="Bob Smith",
        course_name="Web Development Masterclass",
        issue_date="December 02, 2025",
        certificate_number="CERT-2025-101"
    )
    print(f"✓ Custom certificate created: {filepath}")
    
    # Example 3: Batch generation
    print("\n[3] Generating batch of certificates...")
    recipients = [
        {
            "name": "Carol White",
            "course": "Data Science Fundamentals",
            "date": "December 02, 2025",
            "certificate_number": "CERT-2025-102"
        },
        {
            "name": "David Brown",
            "course": "Cloud Computing Essentials",
            "date": "December 02, 2025",
            "certificate_number": "CERT-2025-103"
        },
        {
            "name": "Emma Davis",
            "course": "Artificial Intelligence Basics",
            "date": "December 02, 2025",
            "certificate_number": "CERT-2025-104"
        }
    ]
    
    paths = generator.generate_batch(recipients)
    print(f"✓ Generated {len(paths)} certificates:")
    for path in paths:
        print(f"  - {path.name}")
    
    print("\n" + "=" * 60)
    print("All certificates generated successfully!")
    print(f"Check the 'certificates' folder for PDF files")
    print("=" * 60)


if __name__ == "__main__":
    main()
