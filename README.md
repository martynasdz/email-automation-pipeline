Email Automation Pipeline

A Python automation project that turns incoming PDF order emails into structured MySQL records and CSV exports.

The pipeline monitors an email inbox, downloads matching PDF attachments, extracts the required data, validates it, stores the result in MySQL and sends a processing notification.

Everything runs locally — the current PDF parser does not require OpenAI, Anthropic or another paid AI API.

How it works

Email → PDF → Parse → Validate → MySQL → CSV → Notification

The inbox is checked through IMAP. Only unread emails matching the configured subject prefix are considered, so unrelated messages are left untouched.

Once a matching PDF is found, the program extracts the text, converts the required fields into structured data and stores the result in the database.

Successfully handled emails are marked as read, but they are not deleted or moved.

What is included
Component	Purpose
main.py	Runs the complete pipeline
email_monitor.py	Finds matching emails and downloads PDFs
pdf_parser.py	Extracts and parses PDF data
database.py	Handles MySQL operations
csv_exporter.py	Generates CSV exports
error_handler.py	Logging and email notifications
schema.sql	Creates the required MySQL database structure

The parser uses pdfplumber for text extraction and falls back to PyPDF2 when necessary.

Example

A PDF containing:

Reference Number: ORD-2026-001
First Name: John
Middle Name: A
Last Name: Smith
Date of Birth: 1985-03-15
Search Type: Criminal Background Check
State: California
County: Los Angeles
Source Location: Los Angeles Superior Court
Special Instructions: Expedited processing requested

is converted into structured data, validated and inserted into MySQL.

Values such as dates and U.S. state names are normalized before storage.

Project structure
email-automation-pipeline/
├── config/
│   └── config.example.json
├── database/
│   └── schema.sql
├── output/
│   └── csv_exports/
├── scripts/
│   ├── __init__.py
│   ├── csv_exporter.py
│   ├── database.py
│   ├── email_monitor.py
│   ├── error_handler.py
│   └── pdf_parser.py
├── temp/
│   └── pdf_downloads/
├── .env.example
├── .gitignore
├── main.py
├── requirements.txt
└── README.md
Setup

Clone the repository and create a virtual environment:

python -m venv .venv

On Windows:

.venv\Scripts\activate

Install the dependencies:

pip install -r requirements.txt

Then copy config/config.example.json to config/config.json and .env.example to .env.

Add your own credentials to .env:

EMAIL_ADDRESS=your_email@example.com
EMAIL_PASSWORD=your_gmail_app_password
DB_PASSWORD=your_database_password
SMTP_USER=your_email@example.com
SMTP_PASSWORD=your_gmail_app_password
ALERT_EMAIL=your_alert_email@example.com

The real .env and config/config.json are ignored by Git.

Email filtering

The subject prefix can be configured in config.json.

For example:

"subject_prefix": "Test Order Processing"

will allow emails such as:

Test Order Processing 2

while unrelated unread emails remain untouched.

This was added deliberately so the pipeline can run against an existing mailbox without processing old or unrelated messages.

Database

The project uses MySQL.

Run database/schema.sql to create the required tables and views.

The database keeps the extracted order records together with processing statistics, audit information and error tracking.

The database password itself is loaded from .env.

Running the pipeline

Start it with:

python main.py

During a normal run the application connects to MySQL, scans the inbox, processes new matching PDFs, stores valid records, generates a CSV export and sends a summary email.

Generated CSV files are stored in output/csv_exports/.

Downloaded PDFs are stored in temp/pdf_downloads/.

Both directories are excluded from Git apart from their .gitkeep files.

PDF support

The current parser is designed for text-based, structured PDFs where the expected fields have recognizable labels.

Scanned image-only PDFs are not supported yet because OCR is not currently part of the pipeline.

Security

Credentials are kept outside the source code using .env.

The repository excludes local credentials, virtual environments, runtime logs, downloaded PDFs and generated CSV files through .gitignore.

Public template files are provided instead:

config/config.example.json
.env.example

Tech used

Python · MySQL · IMAP · SMTP · pdfplumber · PyPDF2 · python-dotenv