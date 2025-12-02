# Certificate Generator - Enhanced Edition

A Python-based tool to generate secure, customizable PDF certificates with hidden metadata, random IDs, QR codes, and optional MongoDB tracking for verification.

## Features

- 🎓 Generate professional PDF certificates
- 🔐 **Hidden metadata** embedded in PDF (machine-readable, human-invisible)
- 🎲 **Random, secure certificate IDs** (cryptographically generated)
- 📦 Batch certificate generation
- 🔑 **HMAC checksum** for certificate integrity verification
- 💾 **MongoDB integration** for certificate tracking and verification
- 🔍 **Certificate verification** against stored records
- 🎨 Fully customizable templates
- 📅 Automatic date handling
- 🖥️ CLI and programmatic interfaces

## Installation

### Prerequisites

- Python 3.7+
- pip
- (Optional) MongoDB instance for certificate tracking

### Setup

1. Clone or navigate to the repository:
```bash
cd certificate_gen_ver
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Set up MongoDB connection:
   - Copy `.env.example` to `.env`
   - Update `MONGODB_URI` with your MongoDB connection string
   ```bash
   cp .env.example .env
   # Edit .env with your MongoDB URI
   ```

### MongoDB Setup (Optional)

For local MongoDB with Docker:
```bash
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

Or use MongoDB Atlas (cloud):
- Sign up at https://www.mongodb.com/cloud/atlas
- Create a cluster and get your connection string
- Set `MONGODB_URI` in `.env` or environment variable

## Quick Start

### Option 1: Generate Single Certificate (with Random ID)

Generate a certificate with a secure random ID:

```bash
D:/certificate/certificate_gen_ver/.venv/Scripts/python.exe certificate_generator.py create \
  --name "John Doe" \
  --course "Python Programming" \
  --date "December 02, 2025" \
  --no-store
```

Output:
```
✓ Certificate created: certificates\John_Doe.pdf
  Certificate ID: CERT-20251202-02D1BD47E2A59B4C08B1805E
```

### Option 2: Create and Store in MongoDB

```bash
# Set MONGODB_URI or pass --mongo-uri
D:/certificate/certificate_gen_ver/.venv/Scripts/python.exe certificate_generator.py create \
  --name "Jane Smith" \
  --course "Web Development" \
  --store
```

Certificate will be stored in MongoDB for later verification.

### Option 3: Verify a Certificate

```bash
D:/certificate/certificate_gen_ver/.venv/Scripts/python.exe certificate_generator.py verify \
  --cert-id "CERT-20251202-02D1BD47E2A59B4C08B1805E" \
  --name "John Doe" \
  --course "Python Programming"
```

Output (if valid):
```
✓ Certificate VERIFIED
  ID: CERT-20251202-02D1BD47E2A59B4C08B1805E
  Recipient: John Doe
  Course: Python Programming
  Issued: December 02, 2025
  Issuer: Certificate Authority
```

### Option 4: Batch Generation

```bash
D:/certificate/certificate_gen_ver/.venv/Scripts/python.exe certificate_generator.py batch \
  --input example_recipients.json \
  --store
```

## Security & Hidden Metadata

### What is Hidden Metadata?

Every certificate includes machine-readable hidden metadata that is invisible to the human eye but can be scanned by software:

1. **PDF Metadata** - Certificate ID and HMAC checksum embedded in PDF properties
2. **QR Code** - Encodes certificate data and can optionally link to a verification server
3. **HMAC Checksum** - Cryptographic signature ensuring data integrity

This data is invisible to PDF viewers but verifiable by certificate verification systems.

### Certificate ID Format

All certificate IDs are cryptographically secure random values:
```
CERT-20251202-02D1BD47E2A59B4C08B1805E
│     │         │
│     │         └─ 24-char random hex (192 bits entropy)
│     └────────── Timestamp (YYYYMMDD)
└──────────────── Certificate prefix
```

### Verification Process

When verifying a certificate:

1. Extract the certificate ID from the QR code or PDF metadata
2. Query MongoDB to retrieve the stored record
3. Compare recipient name and course name
4. Return verification status (VALID/INVALID)

### Security Best Practices

- Store MongoDB on a secure, encrypted connection (MongoDB Atlas recommended)
- Use strong credentials for MongoDB access
- Keep the `MONGODB_URI` in `.env` and don't commit it to version control
- Consider adding a certificate invalidation mechanism for revoked certificates

## Customization

### Create Custom Template

1. Generate a template file:
```bash
python certificate_generator.py template --output my_template.json
```

2. Edit `my_template.json`:
```json
{
  "page_size": "landscape",
  "title": "Certificate of Achievement",
  "subtitle": "This is to certify that",
  "issuer": "Your Organization",
  "background_color": [255, 255, 255],
  "text_color": [0, 0, 0],
  "accent_color": [70, 130, 180],
  "border": true,
  "border_width": 3
}
```

3. Use custom template in batch generation:
```bash
python certificate_generator.py batch \
  --input example_recipients.json \
  --template my_template.json
```

### Template Configuration Options

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `page_size` | string | Page layout: "landscape", "portrait", "a4" | landscape |
| `title` | string | Main certificate title | Certificate of Achievement |
| `subtitle` | string | Subtitle text | This is to certify that |
| `issuer` | string | Organization name | Certificate Authority |
| `background_color` | array | RGB color [R, G, B] | [255, 255, 255] |
| `text_color` | array | RGB color for text | [0, 0, 0] |
| `accent_color` | array | RGB color for highlights | [70, 130, 180] |
| `border` | boolean | Enable decorative border | true |
| `border_width` | number | Border width in pixels | 3 |

## Programmatic Usage

Use the certificate generator as a Python module:

```python
from certificate_generator import CertificateGenerator

# Initialize with default template
generator = CertificateGenerator()

# Generate single certificate
filepath = generator.generate_certificate(
    recipient_name="John Doe",
    course_name="Python Mastery",
    issue_date="December 02, 2025",
    certificate_number="CERT-2025-001"
)

# Generate multiple certificates
recipients = [
    {"name": "Alice", "course": "Course 1"},
    {"name": "Bob", "course": "Course 2"},
]
paths = generator.generate_batch(recipients)
```

### Custom Template in Code

```python
custom_template = {
    "title": "Certificate of Excellence",
    "issuer": "Tech Academy",
    "accent_color": (255, 140, 0),
    "border_width": 5,
}

generator = CertificateGenerator(template_config=custom_template)
filepath = generator.generate_certificate(
    recipient_name="Jane Smith",
    course_name="Advanced Web Development"
)
```

## Output

All generated certificates are saved in the `certificates/` folder as PDF files.

Filename format: `{recipient_name}.pdf` (spaces replaced with underscores)

Example: `John_Doe.pdf`

## Running Tests

Execute the test suite:

```bash
python -m pytest test_certificate_generator.py -v
```

Or with unittest:

```bash
python -m unittest test_certificate_generator.py -v
```

## CLI Commands Reference

### Create Single Certificate

```bash
python certificate_generator.py create \
  --name "Recipient Name" \
  --course "Course Name" \
  [--date "Date"] \
  [--number "CERT-001"] \
  [--output "filename.pdf"]
```

### Batch Generation

```bash
python certificate_generator.py batch \
  --input recipients.json \
  [--template template.json]
```

### Generate Template File

```bash
python certificate_generator.py template [--output template.json]
```

### Generate Sample Recipients File

```bash
python certificate_generator.py recipients [--output recipients.json]
```

## Color Reference

Popular accent colors (RGB):

| Color | RGB | Hex |
|-------|-----|-----|
| Steel Blue | (70, 130, 180) | #4682b4 |
| Dark Gold | (184, 134, 11) | #b8860b |
| Forest Green | (34, 139, 34) | #228b22 |
| Dark Red | (139, 0, 0) | #8b0000 |
| Navy | (0, 0, 128) | #000080 |
| Dark Orange | (255, 140, 0) | #ff8c00 |

## Project Structure

```
certificate_gen_ver/
├── certificate_generator.py      # Main module
├── quick_start.py               # Quick start demo
├── test_certificate_generator.py # Unit tests
├── example_recipients.json       # Sample recipients
├── example_template.json         # Sample template
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## Troubleshooting

### Module not found errors

Ensure all dependencies are installed:
```bash
pip install -r requirements.txt
```

### Certificates folder not created

The `certificates/` folder is created automatically on first run. If issues persist, create it manually:
```bash
mkdir certificates
```

### Special characters in names

The generator automatically sanitizes filenames. Special characters are removed to create valid file names.

## Examples

### Generate a professional award certificate

```python
from certificate_generator import CertificateGenerator

template = {
    "title": "Award of Recognition",
    "subtitle": "Presented to",
    "issuer": "National Achievement Society",
    "accent_color": (184, 134, 11),  # Gold
    "border_width": 5,
}

gen = CertificateGenerator(template_config=template)
gen.generate_certificate(
    recipient_name="Dr. Jane Smith",
    course_name="Outstanding Contribution to Science",
    certificate_number="AWD-2025-001"
)
```

### Batch generate for a class

```bash
# recipients.json
[
  {"name": "Student A", "course": "CS101", "certificate_number": "STU-2025-001"},
  {"name": "Student B", "course": "CS101", "certificate_number": "STU-2025-002"},
  {"name": "Student C", "course": "CS101", "certificate_number": "STU-2025-003"}
]

# Run
python certificate_generator.py batch --input recipients.json
```

## License

MIT License - Feel free to use and modify for your needs.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues, questions, or feature requests, please open an issue on the repository.
