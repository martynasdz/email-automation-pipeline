"""
CSV Export Script
Exports database records to CSV files formatted for Digital Delve Harvest
"""

import csv
import os
import logging
from typing import List, Dict
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CSVExporter:
    """Exports database records to CSV files"""

    def __init__(self, config: Dict):
        """
        Initialize CSV exporter

        Args:
            config: Configuration dictionary
        """
        self.config = config['output']
        self.csv_directory = self.config['csv_directory']
        self.csv_filename_prefix = self.config.get('csv_filename_prefix', 'digital_delve_export_')

        # Create output directory if it doesn't exist
        os.makedirs(self.csv_directory, exist_ok=True)

        # CSV column headers for Digital Delve Harvest format
        self.csv_headers = [
            'Reference',
            'FirstName',
            'MiddleName',
            'LastName',
            'DOB',
            'SearchType',
            'State',
            'County',
            'SourceLocation',
            'SpecialInstructions',
            'ProcessingDate'
        ]

    def export_records(self, records: List[Dict]) -> str:
        """
        Export records to CSV file

        Args:
            records: List of record dictionaries

        Returns:
            Path to generated CSV file
        """
        try:
            if not records:
                logger.warning("No records to export")
                return ""

            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{self.csv_filename_prefix}{timestamp}.csv"
            filepath = os.path.join(self.csv_directory, filename)

            # Write CSV file
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.csv_headers)
                writer.writeheader()

                for record in records:
                    row = self._format_record_for_csv(record)
                    writer.writerow(row)

            logger.info(f"Exported {len(records)} records to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            return ""

    def _format_record_for_csv(self, record: Dict) -> Dict:
        """
        Format database record for CSV export

        Args:
            record: Database record dictionary

        Returns:
            Formatted dictionary for CSV
        """
        return {
            'Reference': record.get('reference_number', ''),
            'FirstName': record.get('first_name', ''),
            'MiddleName': record.get('middle_name', ''),
            'LastName': record.get('last_name', ''),
            'DOB': self._format_date(record.get('date_of_birth')),
            'SearchType': record.get('search_type', ''),
            'State': record.get('state', ''),
            'County': record.get('county', ''),
            'SourceLocation': record.get('source_location', ''),
            'SpecialInstructions': record.get('special_instructions', ''),
            'ProcessingDate': self._format_datetime(record.get('created_at'))
        }

    def _format_date(self, date_value) -> str:
        """
        Format date value for CSV

        Args:
            date_value: Date value (string or datetime)

        Returns:
            Formatted date string (YYYY-MM-DD)
        """
        if not date_value:
            return ''

        if isinstance(date_value, str):
            # Try to parse and reformat
            try:
                dt = datetime.strptime(date_value, '%Y-%m-%d')
                return dt.strftime('%Y-%m-%d')
            except:
                return date_value
        elif hasattr(date_value, 'strftime'):
            return date_value.strftime('%Y-%m-%d')

        return str(date_value)

    def _format_datetime(self, datetime_value) -> str:
        """
        Format datetime value for CSV

        Args:
            datetime_value: Datetime value

        Returns:
            Formatted datetime string (YYYY-MM-DD HH:MM:SS)
        """
        if not datetime_value:
            return ''

        if isinstance(datetime_value, str):
            return datetime_value
        elif hasattr(datetime_value, 'strftime'):
            return datetime_value.strftime('%Y-%m-%d %H:%M:%S')

        return str(datetime_value)

    def export_successful_records_by_date_range(self, db_manager, start_date: str, end_date: str) -> str:
        """
        Export successful records within date range

        Args:
            db_manager: Database manager instance
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Path to generated CSV file
        """
        try:
            # Get records from database
            records = db_manager.get_successful_records(start_date, end_date)

            if not records:
                logger.warning(f"No successful records found between {start_date} and {end_date}")
                return ""

            # Export to CSV
            filepath = self.export_records(records)

            # Update statistics
            db_manager.update_processing_stats({
                'csvs_generated': 1
            })

            return filepath

        except Exception as e:
            logger.error(f"Error exporting records by date range: {e}")
            return ""

    def export_failed_records(self, db_manager, limit: int = 100) -> str:
        """
        Export failed records for manual review

        Args:
            db_manager: Database manager instance
            limit: Maximum number of records to export

        Returns:
            Path to generated CSV file
        """
        try:
            # Get failed records from database
            records = db_manager.get_failed_records(limit)

            if not records:
                logger.warning("No failed records found")
                return ""

            # Generate filename for failed records
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"failed_records_{timestamp}.csv"
            filepath = os.path.join(self.csv_directory, filename)

            # Write CSV file with additional error columns
            headers = self.csv_headers + ['ErrorMessage', 'ProcessingStatus']

            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()

                for record in records:
                    row = self._format_record_for_csv(record)
                    row['ErrorMessage'] = record.get('error_message', '')
                    row['ProcessingStatus'] = record.get('processing_status', '')
                    writer.writerow(row)

            logger.info(f"Exported {len(records)} failed records to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error exporting failed records: {e}")
            return ""

    def cleanup_old_exports(self, days_to_keep: int = 30) -> int:
        """
        Clean up old CSV export files

        Args:
            days_to_keep: Number of days to keep files

        Returns:
            Number of files deleted
        """
        try:
            deleted_count = 0
            cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)

            for filename in os.listdir(self.csv_directory):
                if filename.endswith('.csv'):
                    filepath = os.path.join(self.csv_directory, filename)
                    file_mtime = os.path.getmtime(filepath)

                    if file_mtime < cutoff_date:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.info(f"Deleted old export file: {filename}")

            logger.info(f"Cleaned up {deleted_count} old export files")
            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up old exports: {e}")
            return 0


def main():
    """Test function for CSV exporter"""
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Create exporter
    exporter = CSVExporter(config)

    # Test with sample data
    sample_records = [
        {
            'reference_number': 'ORD-001',
            'first_name': 'John',
            'middle_name': 'A',
            'last_name': 'Smith',
            'date_of_birth': '1985-03-15',
            'search_type': 'Criminal Search',
            'state': 'CA',
            'county': 'Los Angeles',
            'source_location': 'Los Angeles Court',
            'special_instructions': 'Expedited',
            'created_at': datetime.now()
        }
    ]

    filepath = exporter.export_records(sample_records)
    print(f"Test export created: {filepath}")


if __name__ == "__main__":
    main()
