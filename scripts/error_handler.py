"""
Error Handler Script
Handles error notifications and alerts via email
"""

import json
import logging
import os
import smtplib
import traceback

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Optional


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Handles error notifications and alerts."""

    def __init__(self, config: Dict):
        """
        Initialize error handler.

        Args:
            config: Complete application configuration dictionary.
        """

        self.config = config["notifications"]

        self.alert_email = self.config["alert_email"]
        self.smtp_server = self.config["smtp_server"]
        self.smtp_port = self.config["smtp_port"]
        self.smtp_user = self.config["smtp_user"]
        self.smtp_password = self.config["smtp_password"]

        self.from_name = self.config.get(
            "from_name",
            "Email Automation System"
        )

    # ---------------------------------------------------------
    # Error notification
    # ---------------------------------------------------------

    def send_error_alert(
        self,
        error_details: Dict,
        pdf_path: Optional[str] = None
    ) -> bool:
        """
        Send an error notification email.

        Args:
            error_details: Dictionary containing error information.
            pdf_path: Optional PDF file to attach.

        Returns:
            True if email was sent successfully.
        """

        try:

            msg = MIMEMultipart()

            msg["From"] = (
                f"{self.from_name} <{self.smtp_user}>"
            )

            msg["To"] = self.alert_email

            message_id = error_details.get(
                "message_id",
                "Unknown"
            )

            msg["Subject"] = (
                f"ERROR: Email Processing Failed - "
                f"{message_id}"
            )

            body = self._create_error_email_body(
                error_details
            )

            msg.attach(
                MIMEText(
                    body,
                    "html",
                    "utf-8"
                )
            )

            # Attach failed PDF if available
            if (
                pdf_path
                and os.path.exists(pdf_path)
            ):

                with open(
                    pdf_path,
                    "rb"
                ) as file:

                    part = MIMEApplication(
                        file.read(),
                        Name=os.path.basename(
                            pdf_path
                        )
                    )

                part["Content-Disposition"] = (
                    f'attachment; '
                    f'filename="{os.path.basename(pdf_path)}"'
                )

                msg.attach(part)

                logger.info(
                    "Attached PDF: %s",
                    pdf_path
                )

            self._send_email(msg)

            logger.info(
                "Error alert sent to %s",
                self.alert_email
            )

            return True

        except Exception as exc:

            logger.error(
                "Failed to send error alert: %s",
                exc
            )

            return False

    # ---------------------------------------------------------
    # Success notification
    # ---------------------------------------------------------

    def send_success_notification(
        self,
        summary: Dict
    ) -> bool:
        """
        Send success notification email.

        Args:
            summary: Pipeline processing statistics.

        Returns:
            True if email was sent successfully.
        """

        try:

            msg = MIMEMultipart()

            msg["From"] = (
                f"{self.from_name} <{self.smtp_user}>"
            )

            msg["To"] = self.alert_email

            successful_records = summary.get(
                "records_successful",
                summary.get(
                    "processed_count",
                    0
                )
            )

            msg["Subject"] = (
                "SUCCESS: Email Processing Completed - "
                f"{successful_records} records"
            )

            body = self._create_success_email_body(
                summary
            )

            msg.attach(
                MIMEText(
                    body,
                    "html",
                    "utf-8"
                )
            )

            self._send_email(msg)

            logger.info(
                "Success notification sent to %s",
                self.alert_email
            )

            return True

        except Exception as exc:

            logger.error(
                "Failed to send success notification: %s",
                exc
            )

            return False

    # ---------------------------------------------------------
    # Error email HTML
    # ---------------------------------------------------------

    def _create_error_email_body(
        self,
        error_details: Dict
    ) -> str:
        """
        Create HTML body for error email.

        Args:
            error_details: Error information dictionary.

        Returns:
            HTML email body.
        """

        html = """
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #ffffff;
                    color: #222222;
                }}

                .error-box {{
                    background-color: #ffeeee;
                    border: 1px solid #ff0000;
                    padding: 15px;
                    margin: 10px 0;
                }}

                .info-box {{
                    background-color: #f0f0f0;
                    border: 1px solid #cccccc;
                    padding: 15px;
                    margin: 10px 0;
                }}

                table {{
                    border-collapse: collapse;
                    width: 100%;
                }}

                td {{
                    padding: 8px;
                    border-bottom: 1px solid #dddddd;
                }}
            </style>
        </head>

        <body>

            <h2>Email Processing Error Alert</h2>

            <div class="error-box">
                <strong>Error Type:</strong>
                {error_type}
                <br/>

                <strong>Error Message:</strong>
                {error_message}
            </div>

            <div class="info-box">

                <h3>Email Details</h3>

                <table>

                    <tr>
                        <td>
                            <strong>Message ID:</strong>
                        </td>
                        <td>
                            {message_id}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>Subject:</strong>
                        </td>
                        <td>
                            {subject}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>Sender:</strong>
                        </td>
                        <td>
                            {sender}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>PDF Filename:</strong>
                        </td>
                        <td>
                            {pdf_filename}
                        </td>
                    </tr>

                </table>

            </div>

            <div class="info-box">

                <h3>Validation Errors</h3>

                <ul>
                    {validation_errors}
                </ul>

            </div>

            <p>
                <em>
                    Please review the attached PDF
                    and process manually if needed.
                </em>
            </p>

            <hr/>

            <p>
                <small>
                    This is an automated message from
                    the Email Automation System.
                </small>
            </p>

        </body>
        </html>
        """

        validation_errors = error_details.get(
            "validation_errors",
            []
        )

        if validation_errors:

            validation_list = "\n".join(
                f"<li>{error}</li>"
                for error in validation_errors
            )

        else:

            validation_list = (
                "<li>No specific validation errors</li>"
            )

        return html.format(
            error_type=error_details.get(
                "error_type",
                "Unknown"
            ),
            error_message=error_details.get(
                "error_message",
                "No error message"
            ),
            message_id=error_details.get(
                "message_id",
                "Unknown"
            ),
            subject=error_details.get(
                "subject",
                "Unknown"
            ),
            sender=error_details.get(
                "sender",
                "Unknown"
            ),
            pdf_filename=error_details.get(
                "pdf_filename",
                "Unknown"
            ),
            validation_errors=validation_list
        )

    # ---------------------------------------------------------
    # Success email HTML
    # ---------------------------------------------------------

    def _create_success_email_body(
        self,
        summary: Dict
    ) -> str:
        """
        Create HTML body for success notification.

        Args:
            summary: Pipeline processing statistics.

        Returns:
            HTML email body.
        """

        html = """
        <html>
        <head>
            <style>

                body {{
                    font-family: Arial, sans-serif;
                    background-color: #ffffff;
                    color: #222222;
                }}

                .success-box {{
                    background-color: #eeffee;
                    border: 1px solid #00aa00;
                    padding: 15px;
                    margin: 10px 0;
                }}

                .info-box {{
                    background-color: #f0f0f0;
                    border: 1px solid #cccccc;
                    padding: 15px;
                    margin: 10px 0;
                }}

                table {{
                    border-collapse: collapse;
                    width: 100%;
                }}

                td {{
                    padding: 8px;
                    border-bottom: 1px solid #dddddd;
                }}

            </style>
        </head>

        <body>

            <h2>
                Email Processing Completed Successfully
            </h2>

            <div class="success-box">

                <strong>
                    Processing Summary:
                </strong>

                {processed_count}
                records processed successfully

            </div>

            <div class="info-box">

                <h3>Statistics</h3>

                <table>

                    <tr>
                        <td>
                            <strong>
                                Emails Processed:
                            </strong>
                        </td>
                        <td>
                            {emails_processed}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>
                                PDFs Downloaded:
                            </strong>
                        </td>
                        <td>
                            {pdfs_downloaded}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>
                                Records Extracted:
                            </strong>
                        </td>
                        <td>
                            {records_extracted}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>
                                Records Successful:
                            </strong>
                        </td>
                        <td>
                            {records_successful}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>
                                Records Failed:
                            </strong>
                        </td>
                        <td>
                            {records_failed}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>
                                CSV Files Generated:
                            </strong>
                        </td>
                        <td>
                            {csvs_generated}
                        </td>
                    </tr>

                    <tr>
                        <td>
                            <strong>
                                Processing Time:
                            </strong>
                        </td>
                        <td>
                            {processing_time}s
                        </td>
                    </tr>

                </table>

            </div>

            <p>
                <em>
                    CSV export files have been generated
                    and are ready for downstream processing.
                </em>
            </p>

            <hr/>

            <p>
                <small>
                    This is an automated message from
                    the Email Automation System.
                </small>
            </p>

        </body>
        </html>
        """

        processed_count = summary.get(
            "records_successful",
            summary.get(
                "processed_count",
                0
            )
        )

        processing_time = summary.get(
            "processing_time",
            0
        )

        if isinstance(
            processing_time,
            (int, float)
        ):
            processing_time = round(
                processing_time,
                2
            )

        return html.format(
            processed_count=processed_count,
            emails_processed=summary.get(
                "emails_processed",
                0
            ),
            pdfs_downloaded=summary.get(
                "pdfs_downloaded",
                0
            ),
            records_extracted=summary.get(
                "records_extracted",
                0
            ),
            records_successful=summary.get(
                "records_successful",
                0
            ),
            records_failed=summary.get(
                "records_failed",
                0
            ),
            csvs_generated=summary.get(
                "csvs_generated",
                0
            ),
            processing_time=processing_time
        )

    # ---------------------------------------------------------
    # SMTP
    # ---------------------------------------------------------

    def _send_email(
        self,
        msg: MIMEMultipart
    ) -> None:
        """Send email through configured SMTP server."""

        with smtplib.SMTP(
            self.smtp_server,
            self.smtp_port
        ) as server:

            server.starttls()

            server.login(
                self.smtp_user,
                self.smtp_password
            )

            server.send_message(
                msg
            )

    # ---------------------------------------------------------
    # Logging helper
    # ---------------------------------------------------------

    def log_error(
        self,
        error: Exception,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Log exception details.

        Args:
            error: Exception object.
            context: Optional contextual information.

        Returns:
            Dictionary containing error details.
        """

        error_details = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "stack_trace": traceback.format_exc(),
            "context": context or {}
        }

        logger.error(
            "Error occurred: %s - %s",
            error_details["error_type"],
            error_details["error_message"]
        )

        logger.debug(
            "Stack trace: %s",
            error_details["stack_trace"]
        )

        return error_details


# ---------------------------------------------------------
# Standalone test
# ---------------------------------------------------------

def main():
    """Initialize the error handler for a local test."""

    project_root = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

    config_path = os.path.join(
        project_root,
        "config",
        "config.json"
    )

    with open(
        config_path,
        "r",
        encoding="utf-8"
    ) as file:

        config = json.load(file)

    error_handler = ErrorHandler(
        config
    )

    test_error = {
        "message_id": "test-message-id",
        "subject": "Test Subject",
        "sender": "test@example.com",
        "pdf_filename": "test.pdf",
        "error_type": "ValidationError",
        "error_message": (
            "Missing required field: first_name"
        ),
        "validation_errors": [
            "Missing required field: first_name",
            "Invalid date format"
        ]
    }

    print(
        "Error handler initialized successfully."
    )

    print(
        "Test error HTML generated:",
        bool(
            error_handler._create_error_email_body(
                test_error
            )
        )
    )


if __name__ == "__main__":
    main()
