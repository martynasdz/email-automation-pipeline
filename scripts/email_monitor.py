"""
Email Monitor Script

Monitors an IMAP inbox for emails containing PDF attachments.

Safe behavior:
- Only searches unread emails matching configured subject prefix
- Verifies subject prefix before processing
- Downloads PDF attachments
- Checks MySQL for duplicate Message-IDs
- Marks known duplicates as read
- Does NOT delete or move emails
"""

import email
import hashlib
import imaplib
import json
import logging
import os

from email.header import decode_header
from typing import Dict, List, Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class EmailMonitor:
    """Monitor an IMAP inbox for PDF order emails."""

    def __init__(self, config: Dict):
        """
        Initialize email monitor.

        Args:
            config: Complete application configuration.
        """

        self.config = config["email"]

        self.imap_server = self.config["imap_server"]
        self.imap_port = self.config["imap_port"]
        self.email_address = self.config["email_address"]
        self.password = self.config["password"]

        self.inbox_folder = self.config.get(
            "inbox_folder",
            "INBOX"
        )

        self.processed_folder = self.config.get(
            "processed_folder",
            "Processed"
        )

        self.subject_prefix = self.config.get(
            "subject_prefix",
            ""
        ).strip()

        self.use_oauth = self.config.get(
            "use_oauth",
            False
        )

        self.temp_directory = config["output"]["temp_directory"]

        os.makedirs(
            self.temp_directory,
            exist_ok=True
        )

        self.connection = None

    # ---------------------------------------------------------
    # Connection
    # ---------------------------------------------------------

    def connect(self) -> bool:
        """Connect to configured IMAP server."""

        try:

            if self.use_oauth:

                logger.info(
                    "Connecting with OAuth2..."
                )

                return self._connect_oauth()

            logger.info(
                "Connecting to IMAP server: %s",
                self.imap_server
            )

            self.connection = imaplib.IMAP4_SSL(
                self.imap_server,
                self.imap_port
            )

            self.connection.login(
                self.email_address,
                self.password
            )

            logger.info(
                "Successfully connected to IMAP server"
            )

            return True

        except Exception as exc:

            logger.error(
                "Failed to connect to IMAP server: %s",
                exc
            )

            return False

    def _connect_oauth(self) -> bool:
        """Placeholder for future OAuth2 support."""

        logger.warning(
            "OAuth2 authentication not yet implemented"
        )

        return False

    def disconnect(self) -> None:
        """Disconnect safely from IMAP."""

        if not self.connection:
            return

        try:

            try:
                self.connection.close()
            except Exception:
                pass

            self.connection.logout()

            logger.info(
                "Disconnected from IMAP server"
            )

        except Exception as exc:

            logger.warning(
                "Error while disconnecting from IMAP: %s",
                exc
            )

        finally:

            self.connection = None

    # ---------------------------------------------------------
    # Mailbox operations
    # ---------------------------------------------------------

    def select_folder(
        self,
        folder: str
    ) -> bool:
        """Select an IMAP folder."""

        try:

            status, _ = self.connection.select(
                folder
            )

            if status != "OK":

                logger.error(
                    "Failed to select folder: %s",
                    folder
                )

                return False

            logger.info(
                "Selected folder: %s",
                folder
            )

            return True

        except Exception as exc:

            logger.error(
                "Failed to select folder %s: %s",
                folder,
                exc
            )

            return False

    def search_unread_emails(
        self
    ) -> List[bytes]:
        """
        Search unread emails.

        If subject_prefix is configured, IMAP only returns
        unread emails whose subject contains that text.
        """

        try:

            if self.subject_prefix:

                status, message_ids = self.connection.search(
                    None,
                    "UNSEEN",
                    "SUBJECT",
                    f'"{self.subject_prefix}"'
                )

                logger.info(
                    "Searching unread emails with subject prefix: %s",
                    self.subject_prefix
                )

            else:

                status, message_ids = self.connection.search(
                    None,
                    "UNSEEN"
                )

                logger.warning(
                    "No subject_prefix configured. "
                    "Searching all unread emails."
                )

            if status != "OK":

                logger.error(
                    "Email search failed with status: %s",
                    status
                )

                return []

            ids = message_ids[0].split()

            logger.info(
                "Found %s matching unread emails",
                len(ids)
            )

            return ids

        except Exception as exc:

            logger.error(
                "Error searching emails: %s",
                exc
            )

            return []

    # ---------------------------------------------------------
    # Email parsing
    # ---------------------------------------------------------

    def get_email_details(
        self,
        imap_message_id: bytes
    ) -> Dict:
        """
        Read email metadata without marking email as read.

        BODY.PEEK[] prevents normal inspection from changing
        the unread state.
        """

        try:

            status, msg_data = self.connection.fetch(
                imap_message_id,
                "(BODY.PEEK[])"
            )

            if status != "OK":

                logger.error(
                    "Failed to fetch message %s",
                    imap_message_id
                )

                return {}

            raw_bytes = None

            for response_part in msg_data:

                if isinstance(
                    response_part,
                    tuple
                ):

                    raw_bytes = response_part[1]
                    break

            if not raw_bytes:

                logger.error(
                    "No email body returned for message %s",
                    imap_message_id
                )

                return {}

            email_message = email.message_from_bytes(
                raw_bytes
            )

            subject = self._decode_header(
                email_message.get("Subject")
            )

            sender = self._decode_header(
                email_message.get("From")
            )

            email_date = email_message.get(
                "Date"
            )

            message_id = email_message.get(
                "Message-ID"
            )

            if not message_id:

                fallback_string = (
                    f"{sender}|{subject}|{email_date}"
                )

                fallback_hash = hashlib.sha256(
                    fallback_string.encode(
                        "utf-8",
                        errors="ignore"
                    )
                ).hexdigest()

                message_id = (
                    f"<generated-{fallback_hash}@local>"
                )

            return {
                "message_id": message_id,
                "subject": subject,
                "sender": sender,
                "date": email_date,
                "raw_message": email_message,
                "imap_message_id": imap_message_id
            }

        except Exception as exc:

            logger.error(
                "Error getting email details: %s",
                exc
            )

            return {}

    @staticmethod
    def _decode_header(
        header: Optional[str]
    ) -> str:
        """Decode MIME encoded email header."""

        if not header:
            return ""

        decoded_parts = decode_header(
            header
        )

        output = ""

        for part, encoding in decoded_parts:

            if isinstance(
                part,
                bytes
            ):

                try:

                    output += part.decode(
                        encoding or "utf-8",
                        errors="ignore"
                    )

                except Exception:

                    output += part.decode(
                        "utf-8",
                        errors="ignore"
                    )

            else:

                output += str(part)

        return output

    def subject_matches(
        self,
        subject: str
    ) -> bool:
        """
        Verify that email subject starts with configured prefix.

        This is a second safety check in addition to IMAP search.
        """

        if not self.subject_prefix:
            return True

        return subject.lower().startswith(
            self.subject_prefix.lower()
        )

    # ---------------------------------------------------------
    # PDF attachment handling
    # ---------------------------------------------------------

    @staticmethod
    def has_pdf_attachment(
        email_message
    ) -> bool:
        """Check whether email contains a PDF attachment."""

        for part in email_message.walk():

            if (
                part.get_content_maintype()
                == "multipart"
            ):
                continue

            filename = part.get_filename()

            if (
                filename
                and
                filename.lower().endswith(".pdf")
            ):
                return True

        return False

    def download_pdf_attachments(
        self,
        email_message,
        message_id: str
    ) -> List[str]:
        """Download all PDF attachments from an email."""

        downloaded_files = []

        try:

            for part in email_message.walk():

                if (
                    part.get_content_maintype()
                    == "multipart"
                ):
                    continue

                filename = part.get_filename()

                if not filename:
                    continue

                filename = self._decode_header(
                    filename
                )

                if not filename.lower().endswith(
                    ".pdf"
                ):
                    continue

                safe_filename = (
                    self._sanitize_filename(
                        filename
                    )
                )

                message_hash = hashlib.md5(
                    message_id.encode(
                        "utf-8",
                        errors="ignore"
                    )
                ).hexdigest()[:8]

                output_filename = (
                    f"{message_hash}_{safe_filename}"
                )

                output_path = os.path.join(
                    self.temp_directory,
                    output_filename
                )

                payload = part.get_payload(
                    decode=True
                )

                if payload is None:

                    logger.warning(
                        "PDF attachment had no payload: %s",
                        filename
                    )

                    continue

                with open(
                    output_path,
                    "wb"
                ) as file:

                    file.write(
                        payload
                    )

                downloaded_files.append(
                    output_path
                )

                logger.info(
                    "Downloaded PDF: %s",
                    output_filename
                )

        except Exception as exc:

            logger.error(
                "Error downloading PDF attachments: %s",
                exc
            )

        return downloaded_files

    @staticmethod
    def _sanitize_filename(
        filename: str
    ) -> str:
        """Remove unsafe filename characters."""

        unsafe_chars = '<>:"/\\|?*'

        for character in unsafe_chars:

            filename = filename.replace(
                character,
                "_"
            )

        return filename.strip()

    # ---------------------------------------------------------
    # Duplicate handling
    # ---------------------------------------------------------

    @staticmethod
    def check_duplicate(
        message_id: str,
        db_connection
    ) -> bool:
        """Check whether Message-ID already exists in MySQL."""

        try:

            cursor = db_connection.cursor()

            cursor.execute(
                """
                SELECT id
                FROM order_records
                WHERE message_id = %s
                LIMIT 1
                """,
                (message_id,)
            )

            result = cursor.fetchone()

            cursor.close()

            return result is not None

        except Exception as exc:

            logger.error(
                "Error checking duplicate: %s",
                exc
            )

            return False

    def mark_as_read(
        self,
        imap_message_id: bytes
    ) -> bool:
        """Mark an email as read without moving or deleting it."""

        try:

            status, _ = self.connection.store(
                imap_message_id,
                "+FLAGS",
                "\\Seen"
            )

            if status != "OK":

                logger.warning(
                    "Failed to mark email as read: %s",
                    imap_message_id
                )

                return False

            logger.info(
                "Email marked as read: %s",
                imap_message_id
            )

            return True

        except Exception as exc:

            logger.warning(
                "Could not mark email as read: %s",
                exc
            )

            return False

    # ---------------------------------------------------------
    # Main inbox scan
    # ---------------------------------------------------------

    def process_inbox(
        self,
        db_connection
    ) -> List[Dict]:
        """
        Find new order emails with PDF attachments.

        Safe filtering:
        1. Must be unread
        2. Must match subject prefix
        3. Must contain PDF
        4. Must not already exist in database
        """

        processed_emails = []

        try:

            if not self.connect():

                logger.error(
                    "Failed to connect to IMAP server"
                )

                return processed_emails

            if not self.select_folder(
                self.inbox_folder
            ):

                logger.error(
                    "Failed to select inbox folder"
                )

                return processed_emails

            message_ids = (
                self.search_unread_emails()
            )

            for imap_message_id in message_ids:

                try:

                    email_details = (
                        self.get_email_details(
                            imap_message_id
                        )
                    )

                    if not email_details:
                        continue

                    subject = email_details[
                        "subject"
                    ]

                    message_id = email_details[
                        "message_id"
                    ]

                    # Second safety check:
                    # subject must START with prefix
                    if not self.subject_matches(
                        subject
                    ):

                        logger.info(
                            "Ignoring email with "
                            "non-matching subject: %s",
                            subject
                        )

                        continue

                    # Already processed previously
                    if self.check_duplicate(
                        message_id,
                        db_connection
                    ):

                        logger.info(
                            "Duplicate email found: %s. "
                            "Marking as read and skipping.",
                            message_id
                        )

                        self.mark_as_read(
                            imap_message_id
                        )

                        continue

                    if not self.has_pdf_attachment(
                        email_details[
                            "raw_message"
                        ]
                    ):

                        logger.info(
                            "Matching email has no "
                            "PDF attachment: %s",
                            message_id
                        )

                        continue

                    pdf_files = (
                        self.download_pdf_attachments(
                            email_details[
                                "raw_message"
                            ],
                            message_id
                        )
                    )

                    if not pdf_files:
                        continue

                    processed_emails.append(
                        {
                            "message_id":
                                message_id,

                            "subject":
                                subject,

                            "sender":
                                email_details[
                                    "sender"
                                ],

                            "date":
                                email_details[
                                    "date"
                                ],

                            "pdf_files":
                                pdf_files,

                            "imap_message_id":
                                imap_message_id
                        }
                    )

                except Exception as exc:

                    logger.error(
                        "Error processing IMAP "
                        "message %s: %s",
                        imap_message_id,
                        exc
                    )

            logger.info(
                "Found %s new matching emails with PDFs",
                len(processed_emails)
            )

        except Exception as exc:

            logger.error(
                "Error processing inbox: %s",
                exc
            )

        finally:

            self.disconnect()

        return processed_emails


# ---------------------------------------------------------
# Standalone connection test
# ---------------------------------------------------------

def main():

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

        config = json.load(
            file
        )

    monitor = EmailMonitor(
        config
    )

    if monitor.connect():

        print(
            "Successfully connected to email server"
        )

        monitor.disconnect()

    else:

        print(
            "Failed to connect to email server"
        )


if __name__ == "__main__":
    main()
