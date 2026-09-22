"""
Database Integration Script
Handles MySQL database operations for storing extracted data
"""

import mysql.connector
from mysql.connector import Error
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages MySQL database operations"""

    def __init__(self, config: Dict):
        """
        Initialize database manager

        Args:
            config: Configuration dictionary
        """
        self.config = config['database']
        self.host = self.config['host']
        self.port = self.config['port']
        self.user = self.config['user']
        self.password = self.config['password']
        self.database = self.config['database']
        self.charset = self.config.get('charset', 'utf8mb4')

        self.connection = None

    def connect(self) -> bool:
        """
        Connect to MySQL database

        Returns:
            bool: True if connection successful
        """
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset
            )
            logger.info("Successfully connected to MySQL database")
            return True
        except Error as e:
            logger.error(f"Failed to connect to MySQL database: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from MySQL database"""
        try:
            if self.connection and self.connection.is_connected():
                self.connection.close()
                logger.info("Disconnected from MySQL database")
        except Error as e:
            logger.error(f"Error disconnecting from database: {e}")

    def insert_order_record(self, email_data: Dict, parsed_data: Dict) -> Optional[int]:
        """
        Insert order record into database

        Args:
            email_data: Email metadata
            parsed_data: Parsed PDF data

        Returns:
            Inserted record ID or None
        """
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return None

            cursor = self.connection.cursor()

            # Determine processing status
            processing_status = 'SUCCESS' if parsed_data.get('is_valid', False) else 'FAILED'
            error_message = None

            if not parsed_data.get('is_valid', False):
                validation_errors = parsed_data.get('validation_errors', [])
                error_message = '; '.join(validation_errors) if validation_errors else 'Validation failed'

            # Insert record
            insert_query = """
            INSERT INTO order_records (
                message_id, reference_number, first_name, middle_name, last_name,
                date_of_birth, search_type, state, county, source_location,
                special_instructions, raw_json, processing_status, error_message,
                pdf_filename, email_subject, email_sender, email_received_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """

            # Parse email date
            email_received_at = self._parse_email_date(email_data.get('date'))

            values = (
                email_data['message_id'],
                parsed_data.get('reference_number'),
                parsed_data.get('first_name'),
                parsed_data.get('middle_name'),
                parsed_data.get('last_name'),
                parsed_data.get('date_of_birth'),
                parsed_data.get('search_type'),
                parsed_data.get('state'),
                parsed_data.get('county'),
                parsed_data.get('source_location'),
                parsed_data.get('special_instructions'),
                json.dumps(parsed_data),
                processing_status,
                error_message,
                parsed_data.get('pdf_filename'),
                email_data.get('subject'),
                email_data.get('sender'),
                email_received_at
            )

            cursor.execute(insert_query, values)
            self.connection.commit()

            record_id = cursor.lastrowid
            logger.info(f"Inserted order record with ID: {record_id}")

            # Log audit entry
            self._log_audit(
                record_id=record_id,
                message_id=email_data['message_id'],
                action_type='DATABASE_INSERT',
                action_description=f"Inserted order record for {email_data['message_id']}",
                status='SUCCESS' if processing_status == 'SUCCESS' else 'FAILED'
            )

            # If failed, log error details
            if processing_status == 'FAILED':
                self._log_error(
                    record_id=record_id,
                    message_id=email_data['message_id'],
                    error_type='VALIDATION_ERROR',
                    error_message=error_message
                )

            return record_id

        except Error as e:
            logger.error(f"Error inserting order record: {e}")
            if self.connection:
                self.connection.rollback()
            return None

    def check_duplicate(self, message_id: str) -> bool:
        """
        Check if message ID already exists in database

        Args:
            message_id: Email message ID

        Returns:
            bool: True if duplicate found
        """
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return False

            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id FROM order_records WHERE message_id = %s",
                (message_id,)
            )
            result = cursor.fetchone()
            return result is not None

        except Error as e:
            logger.error(f"Error checking duplicate: {e}")
            return False

    def get_failed_records(self, limit: int = 100) -> List[Dict]:
        """
        Get failed records for review

        Args:
            limit: Maximum number of records to return

        Returns:
            List of failed record dictionaries
        """
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return []

            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT * FROM order_records
                WHERE processing_status = 'FAILED'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,)
            )

            results = cursor.fetchall()
            return results

        except Error as e:
            logger.error(f"Error getting failed records: {e}")
            return []

    def get_successful_records(self, start_date: str, end_date: str) -> List[Dict]:
        """
        Get successful records within date range

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of successful record dictionaries
        """
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return []

            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT * FROM order_records
                WHERE processing_status = 'SUCCESS'
                AND DATE(created_at) BETWEEN %s AND %s
                ORDER BY created_at ASC
                """,
                (start_date, end_date)
            )

            results = cursor.fetchall()
            return results

        except Error as e:
            logger.error(f"Error getting successful records: {e}")
            return []

    def update_processing_stats(self, stats: Dict) -> bool:
        """
        Update daily processing statistics

        Args:
            stats: Dictionary with statistics

        Returns:
            bool: True if successful
        """
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return False

            cursor = self.connection.cursor()

            today = datetime.now().strftime('%Y-%m-%d')

            # Check if stats exist for today
            cursor.execute(
                "SELECT id FROM processing_stats WHERE stat_date = %s",
                (today,)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing stats
                update_query = """
                UPDATE processing_stats SET
                    emails_processed = emails_processed + %s,
                    pdfs_downloaded = pdfs_downloaded + %s,
                    records_extracted = records_extracted + %s,
                    records_successful = records_successful + %s,
                    records_failed = records_failed + %s,
                    csvs_generated = csvs_generated + %s,
                    api_calls_made = api_calls_made + %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE stat_date = %s
                """
                cursor.execute(update_query, (
                    stats.get('emails_processed', 0),
                    stats.get('pdfs_downloaded', 0),
                    stats.get('records_extracted', 0),
                    stats.get('records_successful', 0),
                    stats.get('records_failed', 0),
                    stats.get('csvs_generated', 0),
                    stats.get('api_calls_made', 0),
                    today
                ))
            else:
                # Insert new stats
                insert_query = """
                INSERT INTO processing_stats (
                    stat_date, emails_processed, pdfs_downloaded, records_extracted,
                    records_successful, records_failed, csvs_generated, api_calls_made
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, (
                    today,
                    stats.get('emails_processed', 0),
                    stats.get('pdfs_downloaded', 0),
                    stats.get('records_extracted', 0),
                    stats.get('records_successful', 0),
                    stats.get('records_failed', 0),
                    stats.get('csvs_generated', 0),
                    stats.get('api_calls_made', 0)
                ))

            self.connection.commit()
            logger.info("Updated processing statistics")
            return True

        except Error as e:
            logger.error(f"Error updating processing stats: {e}")
            if self.connection:
                self.connection.rollback()
            return False

    def _log_audit(self, record_id: int, message_id: str, action_type: str,
                   action_description: str, status: str, metadata: Dict = None) -> bool:
        """
        Log audit entry

        Args:
            record_id: Record ID
            message_id: Email message ID
            action_type: Type of action
            action_description: Description
            status: Action status
            metadata: Additional metadata

        Returns:
            bool: True if successful
        """
        try:
            cursor = self.connection.cursor()

            insert_query = """
            INSERT INTO audit_log (record_id, message_id, action_type, action_description, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            """

            cursor.execute(insert_query, (
                record_id,
                message_id,
                action_type,
                action_description,
                status,
                json.dumps(metadata) if metadata else None
            ))

            self.connection.commit()
            return True

        except Error as e:
            logger.error(f"Error logging audit entry: {e}")
            return False

    def _log_error(self, record_id: int, message_id: str, error_type: str,
                   error_message: str, stack_trace: str = None) -> bool:
        """
        Log error details

        Args:
            record_id: Record ID
            message_id: Email message ID
            error_type: Type of error
            error_message: Error message
            stack_trace: Stack trace

        Returns:
            bool: True if successful
        """
        try:
            cursor = self.connection.cursor()

            insert_query = """
            INSERT INTO error_tracking (record_id, message_id, error_type, error_message, stack_trace)
            VALUES (%s, %s, %s, %s, %s)
            """

            cursor.execute(insert_query, (
                record_id,
                message_id,
                error_type,
                error_message,
                stack_trace
            ))

            self.connection.commit()
            return True

        except Error as e:
            logger.error(f"Error logging error details: {e}")
            return False

    def _parse_email_date(self, date_str: Optional[str]) -> Optional[str]:
        """
        Parse email date string to datetime

        Args:
            date_str: Email date string

        Returns:
            Formatted datetime string or None
        """
        if not date_str:
            return None

        try:
            # Try various date formats
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return None

    def get_connection(self):
        """Get database connection for external use"""
        if not self.connection or not self.connection.is_connected():
            self.connect()
        return self.connection


def main():
    """Test function for database manager"""
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Create database manager
    db_manager = DatabaseManager(config)

    # Test connection
    if db_manager.connect():
        print("Successfully connected to database")
        db_manager.disconnect()
    else:
        print("Failed to connect to database")


if __name__ == "__main__":
    main()
