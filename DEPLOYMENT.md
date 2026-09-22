# Deployment

This file covers the basic steps required to run the Email Automation Pipeline on another machine.

The application is designed to run as a single Python process. Scheduling can be handled separately with Windows Task Scheduler, cron or another job scheduler.

## Requirements

The machine running the pipeline needs:

- Python 3.8+
- MySQL
- internet access
- access to an IMAP mailbox
- access to an SMTP server

The current PDF parser runs locally and does not require an external AI API.

## Installation

Clone or copy the project to the target machine.

Create a virtual environment:

`python -m venv .venv`

Activate it on Windows:

`.venv\Scripts\activate`

On Linux or macOS:

`source .venv/bin/activate`

Install the dependencies:

`pip install -r requirements.txt`

## Configuration

Create the local configuration file by copying:

`config/config.example.json`

to:

`config/config.json`

Then copy:

`.env.example`

to:

`.env`

Add the real credentials to `.env`.

The application currently expects:

    EMAIL_ADDRESS
    EMAIL_PASSWORD
    DB_PASSWORD
    SMTP_USER
    SMTP_PASSWORD
    ALERT_EMAIL

Do not commit the real `.env` or `config/config.json`.

## MySQL

Create the database using:

`database/schema.sql`

The default application configuration expects:

- host: localhost
- port: 3306
- database: email_automation
- user: email_automation

The database password is loaded from `.env`.

Before scheduling the application, run it manually once and confirm that the MySQL connection succeeds.

## Email setup

The default example configuration uses Gmail IMAP and SMTP.

For Gmail, use a Google App Password instead of the normal account password.

The mailbox filter is controlled by `subject_prefix` in `config/config.json`.

Only unread messages matching that prefix are processed.

This should be tested with a dedicated test email before enabling automated runs.

## Manual test

Activate the virtual environment and run:

`python main.py`

A successful test should confirm that the application can:

1. connect to MySQL
2. connect to the inbox
3. find a matching unread email
4. download its PDF attachment
5. parse and validate the PDF
6. insert the record into MySQL
7. generate a CSV export
8. send the processing notification

Runtime information is written to `pipeline.log`.

## Scheduling on Windows

The simplest option on Windows is Task Scheduler.

Create a new task and configure it to run at the required interval.

The program should be executed from the project directory using the Python interpreter inside `.venv`.

Example Python executable:

`.venv\Scripts\python.exe`

Script:

`main.py`

Make sure the task's working directory points to the project directory so relative paths such as `config/`, `output/` and `temp/` resolve correctly.

## Scheduling on Linux

The pipeline can also be triggered with cron.

For example, a cron job can change into the project directory, activate the correct Python environment and execute `main.py`.

The exact interval depends on how frequently the mailbox needs to be checked.

## Generated files

CSV exports are written to:

`output/csv_exports/`

Downloaded PDF files are stored in:

`temp/pdf_downloads/`

These generated files are excluded from Git.

If `delete_temp_files` is enabled in the local configuration, temporary PDFs can be removed after processing.

## Logs

The main runtime log is:

`pipeline.log`

Review this file when troubleshooting failed runs.

Typical things to check include:

- IMAP authentication
- SMTP authentication
- MySQL availability
- malformed or unsupported PDFs
- missing required fields
- filesystem permissions

## Updating the project

When updating the code:

1. stop or disable the scheduled task
2. update the project files
3. activate the virtual environment
4. run `pip install -r requirements.txt`
5. run `python main.py` manually
6. confirm the test completed successfully
7. enable scheduling again

Local `.env` and `config/config.json` files should normally be preserved during updates.

## Security

Keep credentials outside the source code.

The following files should remain local:

- `.env`
- `config/config.json`
`pipeline.log`

Downloaded PDFs and generated CSV exports may also contain private data and should not be committed to a public repository.

Use `.env.example` and `config/config.example.json` only as templates.