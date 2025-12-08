# Certificate Generator & Verification System

A secure, tamper-proof certificate generation and verification system with QR codes, verification tokens, hidden credentials, and integrity checksums.

## Features

✅ **Random Certificate IDs** — Cryptographically secure, unique CERT-YYYYMMDD-{24-hex}  
✅ **QR Codes** — Embedded in PDFs, configurable positions and sizes  
✅ **Verification Tokens** — Unique per certificate for secure verification  
✅ **Hidden Credentials** — Token hash + HMAC checksum in PDF metadata  
✅ **Tamper Detection** — HMAC-SHA256 checksums verify data integrity  
✅ **Local Storage** — Stores credentials in `credentials.json` (no MongoDB required)  
✅ **Batch Generation** — Create multiple certificates from JSON file  
✅ **Custom Templates** — Control layout, colors, fonts, QR position  
✅ **Verification Tool** — Standalone tool to verify certificate authenticity  

---

## Quick Start

### 1. Create a Certificate
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py create --name "John Doe" --course "Python Basics"
```

**Output:**
```
✓ QR code added at position bottom-right: x=697.89, y=36.00, w=108.00, h=108.00
✓ Certificate created: certificates\John_Doe.pdf
  Certificate ID: CERT-20251206-ABC123DEF456
  Verification token (store securely): E7GmFQs5xDLCq_h6xgErbQ
```

### 2. Verify the Certificate
```powershell
& .\.venv\Scripts\python.exe verify_tool.py verify-db `
  --cert-id "CERT-20251206-ABC123DEF456" `
  --name "John Doe" `
  --course "Python Basics" `
  --token "E7GmFQs5xDLCq_h6xgErbQ"
```

**Output:**
```
✓ Certificate VERIFIED
  ID: CERT-20251206-ABC123DEF456
  Recipient: John Doe
  Course: Python Basics
```

---

## Installation

### Prerequisites
- Python 3.12+
- pip

### Setup

1. **Navigate to project:**
```bash
cd D:\certificate\certificate_gen_ver
```

2. **Create virtual environment:**
```bash
python -m venv .venv
```

3. **Activate virtual environment:**

**PowerShell:**
```powershell
.\.venv\Scripts\Activate.ps1
```

**CMD:**
```cmd
.\.venv\Scripts\activate.bat
```

4. **Install dependencies:**
```bash
pip install -r requirements.txt
```

---

## CLI Commands

The system provides 4 main commands:

### Certificate Generation

#### Create Single Certificate
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py create `
  --name "Recipient Name" `
  --course "Course Name" `
  [--date "Month DD, YYYY"] `
  [--output filename.pdf] `
  [--store/--no-store]
```

**Options:**
- `--name` — Recipient name (required)
- `--course` — Course/achievement name (required)
- `--date` — Issue date (defaults to today)
- `--output` — Output filename (defaults to recipient name)
- `--store/--no-store` — Store in JSON (default: true)

**Example:**
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py create `
  --name "Alice Smith" `
  --course "Advanced Python"
```

#### Batch Generation
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py batch `
  --input recipients.json `
  [--template custom_template.json]
```

#### Batch Generation
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py batch `
  --input recipients.json `
  [--template custom_template.json]
```

Create `recipients.json`:
```json
[
  {"name": "Alice Smith", "course": "Python Basics"},
  {"name": "Bob Johnson", "course": "Web Development"},
  {"name": "Carol White", "course": "Data Science"}
]
```

Then run:
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py batch --input recipients.json
```

#### Generate Sample Template
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py template --output my_template.json
```

Edit and use with batch:
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py batch --input recipients.json --template my_template.json
```

#### Generate Sample Recipients File
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py recipients --output recipients.json
```

### Verification

#### Verify by Certificate ID
```powershell
& .\.venv\Scripts\python.exe verify_tool.py verify-db `
  --cert-id "CERT-20251206-ABC123DEF456" `
  --name "John Doe" `
  --course "Python Basics" `
  --token "E7GmFQs5xDLCq_h6xgErbQ"
```

#### Verify from PDF File
Requires PyPDF2:
```bash
pip install PyPDF2
```

Then verify:
```powershell
& .\.venv\Scripts\python.exe verify_tool.py verify-file `
  --file "certificates\John_Doe.pdf" `
  --token "E7GmFQs5xDLCq_h6xgErbQ"
```

#### Process Device Cleanup Data
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py process-device `
  --input device_data.json
```

Read device data from JSON file with cleanup/purge actions and file deletions.

---

## How It Works

### Certificate Creation

1. **Generate Random ID** — Creates `CERT-YYYYMMDD-{24-hex}` format
2. **Generate Token** — Creates unique verification token (URL-safe)
3. **Create PDF** — Draws certificate with QR code
4. **Embed Metadata** — Stores certificate ID, token hash, checksum in PDF
5. **Store Credentials** — Saves to `credentials.json`
6. **Return Token** — Prints token once (only shown at creation)

### Certificate Verification

1. **Extract Metadata** — Reads certificate ID from PDF or request
2. **Lookup Record** — Finds certificate in `credentials.json`
3. **Validate Token** — Compares token hash (if token provided)
4. **Check Checksum** — Verifies data integrity with HMAC-SHA256
5. **Return Result** — Pass/fail with certificate details

---

## Security Features

### Token Management
- **Generated Once** — Unique per certificate, shown only at creation
- **Hashed Storage** — Only hash stored in `credentials.json`, never raw token
- **SHA256 Hash** — Cryptographically secure one-way hashing

### Data Integrity
- **HMAC Checksum** — 16-char HMAC-SHA256 hash of certificate data
- **Tamper Detection** — Checksum mismatch indicates data modification
- **Secret Key** — Uses `CERT_SECRET` environment variable (default: "default-secret")

### Certificate ID
- **Cryptographic Random** — `secrets.token_hex(12)` for 192-bit entropy
- **Timestamp Prefix** — YYYYMMDD format for sortability
- **Unique Format** — CERT-20251206-ABC123DEF456...

---

## File Structure

```
certificate_gen_ver/
├── certificate_generator.py    # Main generation module
├── verify_tool.py              # Standalone verification
├── credentials.json            # Certificate credential store (auto-created)
├── .env                        # Environment config (optional)
├── .gitignore                  # Git rules
├── requirements.txt            # Dependencies
├── certificates/               # Output PDFs
├── README.md                   # This file
└── example_recipients.json     # Sample recipients
```

### credentials.json Format

```json
[
  {
    "certificate_id": "CERT-20251206-ABC123DEF456",
    "recipient_name": "John Doe",
    "course_name": "Python Basics",
    "issue_date": "December 06, 2025",
    "issuer": "Certificate Authority",
    "generated_at": "2025-12-06T10:30:45.123456",
    "credentials": {
      "token_hash": "abc123def456...",
      "checksum": "xyz789"
    },
    "created_at": "2025-12-06T10:30:45.123456",
    "file_path": "certificates\\John_Doe.pdf"
  },
  {
    "device_id": "DEVICE-20251208-ABC123DEF456",
    "action_type": "purge",
    "size_removed": "2.5 GB",
    "timestamp": "2025-12-08T14:30:45.123456",
    "files_deleted_count": 5,
    "files_deleted": [
      "/var/log/application.log",
      "/tmp/cache/temp_files.tmp",
      "/home/user/Downloads/old_backup.zip"
    ],
    "processed_at": "2025-12-08T11:55:47.918775",
    "record_type": "device_cleanup"
  }
]
```

### Device Data Input Format

When processing device cleanup data using `process-device`, the JSON file must contain:

```json
{
  "device_id": "DEVICE-20251208-ABC123DEF456",
  "files_deleted": [
    "/var/log/application.log",
    "/tmp/cache/temp_files.tmp",
    "/home/user/Downloads/old_backup.zip",
    "/opt/app/logs/error_2025-12.log"
  ],
  "size_removed": "2.5 GB",
  "action_type": "purge",
  "timestamp": "2025-12-08T14:30:45.123456"
}
```

**Required Fields:**
- `device_id` (string) — Unique device identifier
- `files_deleted` (array) — List of file paths that were deleted
- `size_removed` (string) — Amount of data removed (e.g., "2.5 GB", "500 MB")
- `action_type` (string) — Type of action: `"clear"` or `"purge"`
- `timestamp` (string) — ISO 8601 timestamp when action occurred

---

## Customization

### Template Configuration

Edit `my_template.json`:
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
  "border_width": 3,
  "qr": true,
  "qr_size": 1.5,
  "qr_margin": 0.5,
  "qr_position": "bottom-right"
}
```

### QR Code Positions

Supported positions:
- `bottom-right` (default)
- `bottom-left`
- `bottom-center`
- `top-right`
- `top-left`
- `top-center`

### QR Code Size

Adjust `qr_size` (in inches):
- `1.0` — 72pt (small)
- `1.5` — 108pt (medium, default)
- `2.0` — 144pt (large)

---

## Examples

### Example 1: Single Certificate
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py create `
  --name "John Smith" `
  --course "Python 101" `
  --date "December 06, 2025"
```

### Example 2: Verify Certificate
```powershell
& .\.venv\Scripts\python.exe verify_tool.py verify-db `
  --cert-id "CERT-20251206-ABC123DEF456" `
  --name "John Smith" `
  --course "Python 101" `
  --token "E7GmFQs5xDLCq_h6xgErbQ"
```

### Example 3: Verify PDF
```powershell
& .\.venv\Scripts\python.exe verify_tool.py verify-file `
  --file "certificates\John_Smith.pdf" `
  --token "E7GmFQs5xDLCq_h6xgErbQ"
```

### Example 4: Process Device Cleanup Data
Create `device_data.json`:
```json
{
  "device_id": "DEVICE-20251208-PROD-ALPHA",
  "files_deleted": [
    "/var/log/application.log",
    "/var/log/error.log",
    "/tmp/session_cache/*",
    "/var/cache/npm/*"
  ],
  "size_removed": "5.8 GB",
  "action_type": "purge",
  "timestamp": "2025-12-08T14:30:45.123456Z"
}
```

Then process:
```powershell
& .\.venv\Scripts\python.exe certificate_generator.py process-device `
  --input device_data.json
```

Output:
```
✓ Device data processed successfully:
  Device ID: DEVICE-20251208-PROD-ALPHA
  Action Type: purge
  Data Removed: 5.8 GB
  Timestamp: 2025-12-08T14:30:45.123456Z
  Files Deleted: 4 file(s)
    1. /var/log/application.log
    2. /var/log/error.log
    3. /tmp/session_cache/*
    4. /var/cache/npm/*
✓ Device record stored in credentials.json
```

  --token "E7GmFQs5xDLCq_h6xgErbQ"
```

---

## Troubleshooting

### PyPDF2 Not Installed
When running `verify-file`:
```bash
pip install PyPDF2
```

### Certificate Not Found
- Check certificate ID matches exactly (case-sensitive)
- Verify name and course match exactly
- Ensure `credentials.json` exists

### Token Mismatch
- Token is case-sensitive and URL-safe base64
- Must be copied exactly from creation output
- Only shown once at creation time

### Invalid Checksum
- Indicates certificate data was modified
- Cannot be verified if data was tampered with

---

## Storage Options

### Local JSON Storage (Default)
- **Location:** `credentials.json`
- **Format:** JSON array
- **No setup required** — automatic
- **Recommended for:** Development, small deployments

### MongoDB Integration (Optional)
```bash
# Set environment variable
$env:MONGODB_URI = "mongodb://localhost:27017/"

# Or create .env file
# MONGODB_URI=mongodb://localhost:27017/
```

If MongoDB is unavailable, system automatically falls back to `credentials.json`.

---

## Environment Variables

Optional configuration:

```bash
# HMAC secret for checksums (default: "default-secret")
$env:CERT_SECRET = "your-secret-key"

# MongoDB connection (optional)
$env:MONGODB_URI = "mongodb://localhost:27017/"
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| reportlab | 4.0.9 | PDF generation |
| qrcode | 7.4.2 | QR code generation |
| click | 8.1.7 | CLI framework |
| pymongo | 4.6.0 | MongoDB (optional) |
| PyPDF2 | 3.0.0 | PDF parsing (optional) |
| pillow | 10.1.0 | Image handling |

---

## Workflow Diagram

```
CREATE CERTIFICATE
    ↓
Generate Random ID
    ↓
Generate Verification Token
    ↓
Create PDF with QR Code
    ↓
Embed Metadata (ID, Token Hash, Checksum)
    ↓
Store in credentials.json
    ↓
Output: PDF + Token
    ↓
    ├─→ VERIFY BY ID
    │   ↓
    │   Lookup in credentials.json
    │   ↓
    │   Validate token (if provided)
    │   ↓
    │   Check checksum
    │   ↓
    │   Result: VERIFIED ✓
    │
    └─→ VERIFY FROM PDF
        ↓
        Extract embedded metadata
        ↓
        Lookup in credentials.json
        ↓
        Validate token (if provided)
        ↓
        Check checksum
        ↓
        Result: VERIFIED ✓
```

---

## System Requirements

- **OS:** Windows, Linux, macOS
- **Python:** 3.12+
- **RAM:** 512 MB minimum
- **Disk:** 100 MB minimum (for certificates)
- **Network:** Optional (MongoDB if used)

---

**Ready to generate secure certificates!** 🎓

