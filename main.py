"""
Main orchestration script for the Email Automation Pipeline.
"""

import imaplib
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

from scripts.config_loader import load_config
from scripts.email_monitor import EmailMonitor
from scripts.pdf_parser import PDFParser
from scripts.database import DatabaseManager
from scripts.csv_exporter import CSVExporter
from scripts.error_handler import ErrorHandler


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

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the pipeline.

        Args:
            config_path: Optional path to a custom config.json file.
        """

        # Load config.json and override sensitive values from .env
        self.config = load_config(config_path)

        # Initialize pipeline components
        self.email_monitor = EmailMonitor(self.config)
        self.pdf_parser = PDFParser(self.config)
        self.db_manager = DatabaseManager(self.config)
        self.csv_exporter = CSVExporter(self.config)
        self.error_handler = ErrorHandler(self.config)

        # Processing settings
        processing_config = self.config.get("processing", {})

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

        # Processing statistics
        self.stats = {
            "emails_processed": 0,
            "pdfs_downloaded": 0,
            "records_extracted": 0,
            "records_successful": 0,
            "records_failed": 0,
            "api_calls_made": 0,
            "csvs_generated": 0
        }

        logger.info("Email Automation Pipeline initialized")

    def run(self) -> None:
        """Run the complete pipeline."""

        start_time = time.time()

        logger.info("=" * 50)
        logger.info("Starting Email Automation Pipeline")
        logger.info("=" * 50)

        try:
            # Connect to MySQL
            if not self.db_manager.connect():
                logger.error(
                    "Failed to connect to database. Aborting pipeline."
                )
                return

            # Process matching emails
            self._process_emails()

            # Export successful records only when new successful records exist
            if self.stats["records_successful"] > 0:
                self._export_successful_records()

            # Save processing statistics
            self.stats["processing_time"] = time.time() - start_time

            self.db_manager.update_processing_stats(self.stats)

            # Send success summary only when something was processed
            if self.stats["records_extracted"] > 0:
                self.error_handler.send_success_notification(self.stats)

            # Optional temporary PDF cleanup
            if self.delete_temp_files:
                self._cleanup_temp_files()

            logger.info("=" * 50)
            logger.info("Pipeline completed successfully")
            logger.info(
                f"Total records processed: "
                f"{self.stats['records_extracted']}"
            )
            logger.info(
                f"Successful: {self.stats['records_successful']}"
            )
            logger.info(
                f"Failed: {self.stats['records_failed']}"
            )
            logger.info(
                f"Processing time: "
                f"{self.stats['processing_time']:.2f}s"
            )
            logger.info("=" * 50)

        except Exception as error:
            logger.exception(f"Pipeline failed: {error}")

            error_details = self.error_handler.log_error(
                error,
                {
                    "pipeline_stage": "main"
                }
            )

            self.error_handler.send_error_alert(error_details)

        finally:
            self.db_manager.disconnect()

    def _process_emails(self) -> List[Dict]:
        """
        Process matching unread emails from the inbox.

        Returns:
            List of successfully processed email dictionaries.
        """

        processed_emails = []

        try:
            # Used by EmailMonitor for duplicate detection
            db_connection = self.db_manager.get_connection()

            logger.info("Checking inbox for new emails...")

            emails = self.email_monitor.process_inbox(
                db_connection
            )

            for email_data in emails:
                message_id = email_data.get(
                    "message_id",
                    "unknown-message-id"
                )

                logger.info(
                    f"Processing email: {message_id}"
                )

                email_successful = True

                try:
                    pdf_files = email_data.get(
                        "pdf_files",
                        []
                    )

                    if not pdf_files:
                        logger.warning(
                            f"No PDF files found for email: "
                            f"{message_id}"
                        )
                        continue

                    for pdf_path in pdf_files:
                        self.stats["pdfs_downloaded"] += 1

                        parsed_data = self._parse_pdf_with_retry(
                            pdf_path
                        )

                        if not parsed_data or not parsed_data.get(
                            "success"
                        ):
                            self.stats["records_failed"] += 1
                            email_successful = False

                            logger.error(
                                f"Failed to parse PDF: {pdf_path}"
                            )

                            error_details = {
                                "message_id": message_id,
                                "subject": email_data.get(
                                    "subject",
                                    ""
                                ),
                                "sender": email_data.get(
                                    "sender",
                                    ""
                                ),
                                "pdf_filename": os.path.basename(
                                    pdf_path
                                ),
                                "error_type": "ParsingError",
                                "error_message": (
                                    parsed_data.get(
                                        "error",
                                        "Unknown parsing error"
                                    )
                                    if parsed_data
                                    else "Unknown parsing error"
                                ),
                                "validation_errors": []
                            }

                            self.error_handler.send_error_alert(
                                error_details,
                                pdf_path
                            )

                            continue

                        self.stats["records_extracted"] += 1

                        # Only count API calls when an external AI
                        # provider is actually being used.
                        provider = (
                            self.config
                            .get("ai", {})
                            .get("provider", "local")
                            .lower()
                        )

                        if provider in {
                            "openai",
                            "anthropic"
                        }:
                            self.stats["api_calls_made"] += 1

                        record_id = (
                            self.db_manager.insert_order_record(
                                email_data,
                                parsed_data
                            )
                        )

                        if not record_id:
                            self.stats["records_failed"] += 1
                            email_successful = False

                            logger.error(
                                "Failed to insert record into database"
                            )

                            continue

                        if parsed_data.get("is_valid"):
                            self.stats["records_successful"] += 1

                            logger.info(
                                f"Successfully processed record: "
                                f"{record_id}"
                            )

                        else:
                            self.stats["records_failed"] += 1
                            email_successful = False

                            logger.warning(
                                f"Record validation failed: "
                                f"{record_id}"
                            )

                            error_details = {
                                "message_id": message_id,
                                "subject": email_data.get(
                                    "subject",
                                    ""
                                ),
                                "sender": email_data.get(
                                    "sender",
                                    ""
                                ),
                                "pdf_filename": parsed_data.get(
                                    "pdf_filename",
                                    os.path.basename(pdf_path)
                                ),
                                "error_type": "ValidationError",
                                "error_message": parsed_data.get(
                                    "validation_errors",
                                    []
                                ),
                                "validation_errors": (
                                    parsed_data.get(
                                        "validation_errors",
                                        []
                                    )
                                )
                            }

                            self.error_handler.send_error_alert(
                                error_details,
                                pdf_path
                            )

                    # Only mark the email as read after all PDFs
                    # belonging to that email were processed successfully.
                    if email_successful:
                        self.stats["emails_processed"] += 1

                        self._mark_email_as_processed(
                            email_data
                        )

                        processed_emails.append(
                            email_data
                        )

                    else:
                        logger.warning(
                            f"Email was not marked as read because "
                            f"processing was not fully successful: "
                            f"{message_id}"
                        )

                except Exception as error:
                    logger.exception(
                        f"Error processing email "
                        f"{message_id}: {error}"
                    )

            return processed_emails

        except Exception as error:
            logger.exception(
                f"Error processing emails: {error}"
            )

            return processed_emails

    def _parse_pdf_with_retry(
        self,
        pdf_path: str
    ) -> Dict:
        """
        Parse a PDF with retry logic.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Parser result dictionary.
        """

        for attempt in range(1, self.max_retries + 1):
            try:
                result = self.pdf_parser.parse_pdf(
                    pdf_path
                )

                if result and result.get("success"):
                    return result

                if attempt < self.max_retries:
                    logger.warning(
                        f"Parse attempt {attempt} failed. "
                        f"Retrying in {self.retry_delay}s..."
                    )

                    time.sleep(
                        self.retry_delay
                    )

            except Exception as error:
                logger.error(
                    f"Parse attempt {attempt} failed "
                    f"with error: {error}"
                )

                if attempt < self.max_retries:
                    time.sleep(
                        self.retry_delay
                    )

        return {
            "success": False,
            "error": "Max retries exceeded"
        }

    def _mark_email_as_processed(
        self,
        email_data: Dict
    ) -> bool:
        """
        Mark a successfully processed email as read.

        The email is found again by its Message-ID so that
        unrelated emails are never modified.

        Args:
            email_data: Email metadata dictionary.

        Returns:
            True if the email was marked as read.
        """

        message_id = email_data.get("message_id")

        if not message_id:
            logger.warning(
                "Cannot mark email as read because "
                "Message-ID is missing"
            )
            return False

        email_config = self.config["email"]

        imap_server = email_config.get(
            "imap_server",
            "imap.gmail.com"
        )

        imap_port = email_config.get(
            "imap_port",
            993
        )

        email_address = email_config.get(
            "email_address",
            ""
        )

        password = email_config.get(
            "password",
            ""
        )

        inbox_folder = email_config.get(
            "inbox_folder",
            "INBOX"
        )

        imap = None

        try:
            imap = imaplib.IMAP4_SSL(
                imap_server,
                imap_port
            )

            imap.login(
                email_address,
                password
            )

            status, _ = imap.select(
                inbox_folder
            )

            if status != "OK":
                logger.error(
                    f"Could not select email folder: "
                    f"{inbox_folder}"
                )
                return False

            status, message_numbers = imap.search(
                None,
                "HEADER",
                "Message-ID",
                f'"{message_id}"'
            )

            if (
                status != "OK"
                or not message_numbers
                or not message_numbers[0]
            ):
                logger.warning(
                    f"Could not find email by Message-ID: "
                    f"{message_id}"
                )
                return False

            matched_ids = message_numbers[0].split()

            for imap_message_id in matched_ids:
                store_status, _ = imap.store(
                    imap_message_id,
                    "+FLAGS",
                    "\\Seen"
                )

                if store_status != "OK":
                    logger.error(
                        f"Failed to mark email as read: "
                        f"{message_id}"
                    )
                    return False

            logger.info(
                f"Email marked as processed/read: "
                f"{message_id}"
            )

            return True

        except Exception as error:
            logger.error(
                f"Failed to mark email as read: "
                f"{message_id} - {error}"
            )

            return False

        finally:
            if imap is not None:
                try:
                    imap.logout()
                except Exception:
                    pass

    def _export_successful_records(self) -> None:
        """
        Export today's successful records to CSV.
        """

        try:
            today = datetime.now().strftime(
                "%Y-%m-%d"
            )

            records = (
                self.db_manager.get_successful_records(
                    today,
                    today
                )
            )

            if not records:
                logger.warning(
                    "No successful records to export"
                )
                return

            csv_path = self.csv_exporter.export_records(
                records
            )

            if csv_path:
                self.stats["csvs_generated"] += 1

                logger.info(
                    f"CSV export created: {csv_path}"
                )

            else:
                logger.warning(
                    "CSV export was not created"
                )

        except Exception as error:
            logger.exception(
                f"Error exporting CSV: {error}"
            )

    def _cleanup_temp_files(self) -> None:
        """
        Remove temporary downloaded PDF files.
        """

        try:
            temp_directory = self.config[
                "output"
            ].get(
                "temp_directory",
                "./temp/pdf_downloads"
            )

            if not os.path.exists(
                temp_directory
            ):
                return

            deleted_count = 0

            for filename in os.listdir(
                temp_directory
            ):
                if not filename.lower().endswith(
                    ".pdf"
                ):
                    continue

                file_path = os.path.join(
                    temp_directory,
                    filename
                )

                os.remove(
                    file_path
                )

                deleted_count += 1

                logger.info(
                    f"Deleted temp file: {filename}"
                )

            logger.info(
                f"Temporary files cleaned up: "
                f"{deleted_count} removed"
            )

        except Exception as error:
            logger.exception(
                f"Error cleaning up temp files: {error}"
            )

    def export_failed_records(
        self,
        limit: int = 100
    ) -> str:
        """
        Export failed database records for manual review.

        Args:
            limit: Maximum number of failed records.

        Returns:
            Generated CSV path or an empty string.
        """

        try:
            if not self.db_manager.connect():
                logger.error(
                    "Failed to connect to database"
                )
                return ""

            return self.csv_exporter.export_failed_records(
                self.db_manager,
                limit
            )

        except Exception as error:
            logger.exception(
                f"Error exporting failed records: {error}"
            )

            return ""

        finally:
            self.db_manager.disconnect()


def main() -> None:
    """Command-line entry point."""

    import argparse

    parser = argparse.ArgumentParser(
        description="Email Automation Pipeline"
    )

    parser.add_argument(
        "--config",
        help="Path to a custom config file",
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
        help="Maximum number of failed records to export"
    )

    args = parser.parse_args()

    pipeline = EmailAutomationPipeline(
        args.config
    )

    if args.export_failed:
        csv_path = pipeline.export_failed_records(
            args.limit
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