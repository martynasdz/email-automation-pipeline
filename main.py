"""
Main Orchestration Script
Coordinates all components of the email automation pipeline
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List

from dotenv import load_dotenv

from scripts.email_monitor import EmailMonitor
from scripts.pdf_parser import PDFParser
from scripts.database import DatabaseManager
from scripts.csv_exporter import CSVExporter
from scripts.error_handler import ErrorHandler


# Configure logging
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class EmailAutomationPipeline:
    """Main pipeline orchestrator."""

    def __init__(self, config_path: str = None):
        """
        Initialize pipeline.

        Args:
            config_path: Optional path to config file.
        """

        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__),
                "config",
                "config.json"
            )

        with open(config_path, "r", encoding="utf-8") as file:
            self.config = json.load(file)

            # Override sensitive values with environment variables
            self.config["email"]["email_address"] = os.getenv(
                "EMAIL_ADDRESS",
                self.config["email"].get("email_address", "")
            )

            self.config["email"]["password"] = os.getenv(
                "EMAIL_PASSWORD",
                self.config["email"].get("password", "")
            )

            self.config["database"]["password"] = os.getenv(
                "DB_PASSWORD",
                self.config["database"].get("password", "")
            )

            self.config["notifications"]["smtp_user"] = os.getenv(
                "SMTP_USER",
                self.config["notifications"].get("smtp_user", "")
            )

            self.config["notifications"]["smtp_password"] = os.getenv(
                "SMTP_PASSWORD",
                self.config["notifications"].get("smtp_password", "")
            )
            self.config["notifications"]["alert_email"] = os.getenv(
                "ALERT_EMAIL",
                self.config["notifications"].get("alert_email", "")
            )

        self.email_monitor = EmailMonitor(self.config)
        self.pdf_parser = PDFParser(self.config)
        self.db_manager = DatabaseManager(self.config)
        self.csv_exporter = CSVExporter(self.config)
        self.error_handler = ErrorHandler(self.config)

        processing_config = self.config.get(
            "processing",
            {}
        )

        self.delete_temp_files = processing_config.get(
            "delete_temp_files",
            True
        )

        self.max_retries = processing_config.get(
            "max_retries",
            3
        )

        self.retry_delay = processing_config.get(
            "retry_delay_seconds",
            30
        )

        self.stats = {
            "emails_processed": 0,
            "pdfs_downloaded": 0,
            "records_extracted": 0,
            "records_successful": 0,
            "records_failed": 0,
            "api_calls_made": 0,
            "csvs_generated": 0
        }

        logger.info(
            "Email Automation Pipeline initialized"
        )

    def run(self) -> None:
        """Run the complete pipeline."""

        start_time = time.time()

        logger.info("=" * 50)
        logger.info(
            "Starting Email Automation Pipeline"
        )
        logger.info("=" * 50)

        try:

            if not self.db_manager.connect():

                logger.error(
                    "Failed to connect to database. "
                    "Aborting pipeline."
                )

                return

            self._process_emails()

            if (
                self.stats["records_successful"]
                > 0
            ):
                self._export_successful_records()

            self.stats["processing_time"] = (
                time.time() - start_time
            )

            self.db_manager.update_processing_stats(
                self.stats
            )

            if (
                self.stats["records_extracted"]
                > 0
            ):

                self.error_handler.send_success_notification(
                    self.stats
                )

            if self.delete_temp_files:
                self._cleanup_temp_files()

            logger.info("=" * 50)
            logger.info(
                "Pipeline completed successfully"
            )

            logger.info(
                "Total records processed: %s",
                self.stats["records_extracted"]
            )

            logger.info(
                "Successful: %s",
                self.stats["records_successful"]
            )

            logger.info(
                "Failed: %s",
                self.stats["records_failed"]
            )

            logger.info(
                "Processing time: %.2fs",
                self.stats["processing_time"]
            )

            logger.info("=" * 50)

        except Exception as exc:

            logger.error(
                "Pipeline failed: %s",
                exc
            )

            error_details = (
                self.error_handler.log_error(
                    exc,
                    {
                        "pipeline_stage": "main"
                    }
                )
            )

            self.error_handler.send_error_alert(
                error_details
            )

        finally:

            self.db_manager.disconnect()

    def _process_emails(
        self
    ) -> List[Dict]:
        """
        Process emails from inbox.

        Email is only marked as read after
        all attached PDFs are processed successfully.
        """

        processed_emails = []

        try:

            db_connection = (
                self.db_manager.get_connection()
            )

            logger.info(
                "Checking inbox for new emails..."
            )

            emails = (
                self.email_monitor.process_inbox(
                    db_connection
                )
            )

            for email_data in emails:

                email_successful = True

                try:

                    logger.info(
                        "Processing email: %s",
                        email_data["message_id"]
                    )

                    pdf_files = email_data.get(
                        "pdf_files",
                        []
                    )

                    if not pdf_files:

                        logger.warning(
                            "Email contains no PDFs: %s",
                            email_data["message_id"]
                        )

                        email_successful = False
                        continue

                    for pdf_path in pdf_files:

                        self.stats[
                            "pdfs_downloaded"
                        ] += 1

                        parsed_data = (
                            self._parse_pdf_with_retry(
                                pdf_path
                            )
                        )

                        if (
                            parsed_data
                            and
                            parsed_data.get(
                                "success"
                            )
                        ):

                            provider = str(
                                self.config.get(
                                    "ai",
                                    {}
                                ).get(
                                    "provider",
                                    "local"
                                )
                            ).lower()

                            if provider in {
                                "openai",
                                "anthropic"
                            }:

                                self.stats[
                                    "api_calls_made"
                                ] += 1

                            self.stats[
                                "records_extracted"
                            ] += 1

                            record_id = (
                                self.db_manager
                                .insert_order_record(
                                    email_data,
                                    parsed_data
                                )
                            )

                            if record_id:

                                if parsed_data.get(
                                    "is_valid"
                                ):

                                    self.stats[
                                        "records_successful"
                                    ] += 1

                                    logger.info(
                                        "Successfully "
                                        "processed record: %s",
                                        record_id
                                    )

                                else:

                                    email_successful = (
                                        False
                                    )

                                    self.stats[
                                        "records_failed"
                                    ] += 1

                                    logger.warning(
                                        "Record validation "
                                        "failed: %s",
                                        record_id
                                    )

                                    validation_errors = (
                                        parsed_data.get(
                                            "validation_errors",
                                            []
                                        )
                                    )

                                    error_details = {
                                        "message_id":
                                            email_data.get(
                                                "message_id"
                                            ),
                                        "subject":
                                            email_data.get(
                                                "subject",
                                                ""
                                            ),
                                        "sender":
                                            email_data.get(
                                                "sender",
                                                ""
                                            ),
                                        "pdf_filename":
                                            parsed_data.get(
                                                "pdf_filename"
                                            ),
                                        "error_type":
                                            "ValidationError",
                                        "error_message":
                                            "; ".join(
                                                validation_errors
                                            )
                                            or
                                            "Validation failed",
                                        "validation_errors":
                                            validation_errors
                                    }

                                    self.error_handler.send_error_alert(
                                        error_details,
                                        pdf_path
                                    )

                            else:

                                email_successful = (
                                    False
                                )

                                self.stats[
                                    "records_failed"
                                ] += 1

                                logger.error(
                                    "Failed to insert "
                                    "record into database"
                                )

                        else:

                            email_successful = False

                            self.stats[
                                "records_failed"
                            ] += 1

                            logger.error(
                                "Failed to parse PDF: %s",
                                pdf_path
                            )

                            if parsed_data:

                                parse_error = (
                                    parsed_data.get(
                                        "error",
                                        "Unknown parsing error"
                                    )
                                )

                            else:

                                parse_error = (
                                    "Unknown parsing error"
                                )

                            error_details = {
                                "message_id":
                                    email_data.get(
                                        "message_id"
                                    ),
                                "subject":
                                    email_data.get(
                                        "subject",
                                        ""
                                    ),
                                "sender":
                                    email_data.get(
                                        "sender",
                                        ""
                                    ),
                                "pdf_filename":
                                    os.path.basename(
                                        pdf_path
                                    ),
                                "error_type":
                                    "ParsingError",
                                "error_message":
                                    parse_error,
                                "validation_errors":
                                    []
                            }

                            self.error_handler.send_error_alert(
                                error_details,
                                pdf_path
                            )

                    if email_successful:

                        self.stats[
                            "emails_processed"
                        ] += 1

                        self._mark_email_as_processed(
                            email_data
                        )

                    processed_emails.append(
                        email_data
                    )

                except Exception as exc:

                    logger.error(
                        "Error processing email %s: %s",
                        email_data.get(
                            "message_id",
                            "Unknown"
                        ),
                        exc
                    )

                    continue

        except Exception as exc:

            logger.error(
                "Error processing emails: %s",
                exc
            )

        return processed_emails

    def _mark_email_as_processed(
        self,
        email_data: Dict
    ) -> bool:
        """
        Safely mark processed email as read.

        Does not delete or expunge the email.
        """

        message_id = email_data.get(
            "message_id"
        )

        if not message_id:

            logger.warning(
                "Cannot mark email as processed: "
                "Message-ID missing"
            )

            return False

        try:

            if not self.email_monitor.connect():

                logger.warning(
                    "Could not reconnect to IMAP"
                )

                return False

            if not self.email_monitor.select_folder(
                self.email_monitor.inbox_folder
            ):

                return False

            status, message_ids = (
                self.email_monitor.connection.search(
                    None,
                    "HEADER",
                    "Message-ID",
                    f'"{message_id}"'
                )
            )

            if status != "OK":

                logger.warning(
                    "Could not find processed email: %s",
                    message_id
                )

                return False

            matching_ids = (
                message_ids[0].split()
                if (
                    message_ids
                    and message_ids[0]
                )
                else []
            )

            if not matching_ids:

                logger.warning(
                    "Processed email not found "
                    "in inbox: %s",
                    message_id
                )

                return False

            imap_message_id = (
                matching_ids[-1]
            )

            status, _ = (
                self.email_monitor.connection.store(
                    imap_message_id,
                    "+FLAGS",
                    "\\Seen"
                )
            )

            if status != "OK":

                logger.warning(
                    "Failed to mark email "
                    "as read: %s",
                    message_id
                )

                return False

            logger.info(
                "Email marked as processed/read: %s",
                message_id
            )

            return True

        except Exception as exc:

            logger.warning(
                "Could not mark email "
                "as processed %s: %s",
                message_id,
                exc
            )

            return False

        finally:

            self.email_monitor.disconnect()

    def _parse_pdf_with_retry(
        self,
        pdf_path: str
    ) -> Dict:
        """
        Parse PDF with retry logic.
        """

        for attempt in range(
            self.max_retries
        ):

            try:

                result = (
                    self.pdf_parser.parse_pdf(
                        pdf_path
                    )
                )

                if (
                    result
                    and
                    result.get(
                        "success"
                    )
                ):

                    return result

                if (
                    attempt
                    < self.max_retries - 1
                ):

                    logger.warning(
                        "Parse attempt %s failed, "
                        "retrying in %ss...",
                        attempt + 1,
                        self.retry_delay
                    )

                    time.sleep(
                        self.retry_delay
                    )

            except Exception as exc:

                logger.error(
                    "Parse attempt %s failed "
                    "with error: %s",
                    attempt + 1,
                    exc
                )

                if (
                    attempt
                    < self.max_retries - 1
                ):

                    time.sleep(
                        self.retry_delay
                    )

        return {
            "success": False,
            "error": "Max retries exceeded"
        }

    def _export_successful_records(
        self
    ) -> None:
        """
        Export today's successful records.
        """

        try:

            today = (
                datetime.now().strftime(
                    "%Y-%m-%d"
                )
            )

            records = (
                self.db_manager
                .get_successful_records(
                    today,
                    today
                )
            )

            if not records:

                logger.warning(
                    "No successful records "
                    "to export"
                )

                return

            csv_path = (
                self.csv_exporter
                .export_records(
                    records
                )
            )

            if csv_path:

                self.stats[
                    "csvs_generated"
                ] += 1

                logger.info(
                    "CSV export created: %s",
                    csv_path
                )

            else:

                logger.warning(
                    "CSV export was not created"
                )

        except Exception as exc:

            logger.error(
                "Error exporting CSV: %s",
                exc
            )

    def _cleanup_temp_files(
        self
    ) -> None:
        """
        Clean up temporary PDF files.
        """

        try:

            temp_directory = (
                self.config[
                    "output"
                ][
                    "temp_directory"
                ]
            )

            if not os.path.exists(
                temp_directory
            ):
                return

            for filename in os.listdir(
                temp_directory
            ):

                if filename.lower().endswith(
                    ".pdf"
                ):

                    file_path = os.path.join(
                        temp_directory,
                        filename
                    )

                    os.remove(
                        file_path
                    )

                    logger.info(
                        "Deleted temp file: %s",
                        filename
                    )

            logger.info(
                "Temporary files cleaned up"
            )

        except Exception as exc:

            logger.error(
                "Error cleaning up temp files: %s",
                exc
            )

    def export_failed_records(
        self,
        limit: int = 100
    ) -> str:
        """
        Export failed records for review.
        """

        try:

            if not self.db_manager.connect():

                logger.error(
                    "Failed to connect to database"
                )

                return ""

            csv_path = (
                self.csv_exporter
                .export_failed_records(
                    self.db_manager,
                    limit
                )
            )

            return csv_path

        except Exception as exc:

            logger.error(
                "Error exporting failed records: %s",
                exc
            )

            return ""

        finally:

            self.db_manager.disconnect()


def main():
    """Main entry point."""

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Email Automation Pipeline"
        )
    )

    parser.add_argument(
        "--config",
        help="Path to config file",
        default=None
    )

    parser.add_argument(
        "--export-failed",
        action="store_true",
        help="Export failed records for review"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limit for failed records export"
    )

    args = parser.parse_args()

    pipeline = EmailAutomationPipeline(
        args.config
    )

    if args.export_failed:

        csv_path = (
            pipeline.export_failed_records(
                args.limit
            )
        )

        if csv_path:

            print(
                f"Failed records exported to: "
                f"{csv_path}"
            )

        else:

            print(
                "No failed records to export"
            )

    else:

        pipeline.run()


if __name__ == "__main__":
    main()
