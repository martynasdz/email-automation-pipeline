"""
PDF Parser Script

Free/local PDF parser for the Email Automation Pipeline.

Extracts text from PDF files using pdfplumber/PyPDF2 and converts
common order-document fields into structured data without requiring
a paid AI API.

Optional AI providers can be added later.
"""

import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, Optional, List

import pdfplumber
from PyPDF2 import PdfReader


# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class PDFParser:
    """Parse PDF documents locally without a paid AI API."""

    def __init__(self, config: Dict):
        """
        Initialize PDF parser.

        Args:
            config: Complete application configuration dictionary.
        """

        self.config = config.get("ai", {})
        self.provider = self.config.get("provider", "local")
        self.model = self.config.get("model", "local-parser")

        processing_config = config.get("processing", {})

        self.required_fields = processing_config.get(
            "required_fields",
            [
                "first_name",
                "last_name",
                "date_of_birth"
            ]
        )

        logger.info(
            "PDFParser initialized with provider: %s",
            self.provider
        )

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def parse_pdf(self, pdf_path: str) -> Dict:
        """
        Parse one PDF document.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            Dictionary containing extracted fields and metadata.
        """

        try:
            logger.info("Parsing PDF: %s", pdf_path)

            if not os.path.exists(pdf_path):
                raise FileNotFoundError(
                    f"PDF file does not exist: {pdf_path}"
                )

            if not pdf_path.lower().endswith(".pdf"):
                raise ValueError(
                    f"File is not a PDF: {pdf_path}"
                )

            text = self._extract_text(pdf_path)

            if not text.strip():
                return {
                    "success": False,
                    "is_valid": False,
                    "error": (
                        "No readable text could be extracted from the PDF. "
                        "The document may be scanned/image-only."
                    ),
                    "validation_errors": [
                        "No readable text found in PDF"
                    ],
                    "pdf_filename": os.path.basename(pdf_path),
                    "parsed_at": datetime.now().isoformat()
                }

            logger.debug("Extracted PDF text:\n%s", text)

            result = self._parse_text(text)

            result["success"] = True
            result["pdf_filename"] = os.path.basename(pdf_path)
            result["parsed_at"] = datetime.now().isoformat()
            result["parser_provider"] = "local"
            result["raw_text"] = text

            result = self._validate_result(result)

            logger.info(
                "Successfully parsed PDF: %s",
                pdf_path
            )

            return result

        except Exception as exc:
            logger.exception(
                "Error parsing PDF %s",
                pdf_path
            )

            return {
                "success": False,
                "is_valid": False,
                "error": str(exc),
                "validation_errors": [str(exc)],
                "pdf_filename": os.path.basename(pdf_path),
                "parsed_at": datetime.now().isoformat()
            }

    # ---------------------------------------------------------
    # PDF text extraction
    # ---------------------------------------------------------

    def _extract_text(self, pdf_path: str) -> str:
        """
        Extract readable text from a PDF.

        pdfplumber is attempted first.
        PyPDF2 is used as a fallback.
        """

        text_parts = []

        # First attempt: pdfplumber
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_number, page in enumerate(pdf.pages, start=1):

                    page_text = page.extract_text()

                    if page_text:
                        text_parts.append(page_text)

            text = "\n".join(text_parts).strip()

            if text:
                logger.info(
                    "Text extracted using pdfplumber"
                )
                return text

        except Exception as exc:
            logger.warning(
                "pdfplumber extraction failed: %s",
                exc
            )

        # Second attempt: PyPDF2
        try:
            reader = PdfReader(pdf_path)

            text_parts = []

            for page in reader.pages:
                page_text = page.extract_text()

                if page_text:
                    text_parts.append(page_text)

            text = "\n".join(text_parts).strip()

            if text:
                logger.info(
                    "Text extracted using PyPDF2 fallback"
                )
                return text

        except Exception as exc:
            logger.warning(
                "PyPDF2 extraction failed: %s",
                exc
            )

        return ""

    # ---------------------------------------------------------
    # Local field parser
    # ---------------------------------------------------------

    def _parse_text(self, text: str) -> Dict:
        """
        Convert extracted text into structured fields.
        """

        cleaned_text = self._clean_text(text)

        result = {
            "reference_number": None,
            "first_name": None,
            "middle_name": None,
            "last_name": None,
            "date_of_birth": None,
            "search_type": None,
            "state": None,
            "county": None,
            "source_location": None,
            "special_instructions": None
        }

        # -----------------------------------------------------
        # Reference number
        # -----------------------------------------------------

        result["reference_number"] = self._find_value(
            cleaned_text,
            [
                r"(?:reference\s*(?:number|no\.?|#)?|ref\s*(?:number|no\.?|#)?|order\s*(?:number|no\.?|#))"
                r"\s*[:\-]\s*([^\n]+)"
            ]
        )

        # -----------------------------------------------------
        # First name
        # -----------------------------------------------------

        result["first_name"] = self._find_value(
            cleaned_text,
            [
                r"first\s*name\s*[:\-]\s*([^\n]+)",
                r"firstname\s*[:\-]\s*([^\n]+)"
            ]
        )

        # -----------------------------------------------------
        # Middle name
        # -----------------------------------------------------

        result["middle_name"] = self._find_value(
            cleaned_text,
            [
                r"middle\s*(?:name|initial)\s*[:\-]\s*([^\n]+)",
                r"middlename\s*[:\-]\s*([^\n]+)"
            ]
        )

        # -----------------------------------------------------
        # Last name
        # -----------------------------------------------------

        result["last_name"] = self._find_value(
            cleaned_text,
            [
                r"last\s*name\s*[:\-]\s*([^\n]+)",
                r"surname\s*[:\-]\s*([^\n]+)",
                r"lastname\s*[:\-]\s*([^\n]+)"
            ]
        )

        # -----------------------------------------------------
        # Full-name fallback
        # -----------------------------------------------------

        if not result["first_name"] or not result["last_name"]:
            full_name = self._find_value(
                cleaned_text,
                [
                    r"(?:subject\s*)?name\s*[:\-]\s*([^\n]+)"
                ]
            )

            if full_name:
                parsed_name = self._parse_full_name(full_name)

                if not result["first_name"]:
                    result["first_name"] = parsed_name["first_name"]

                if not result["middle_name"]:
                    result["middle_name"] = parsed_name["middle_name"]

                if not result["last_name"]:
                    result["last_name"] = parsed_name["last_name"]

        # -----------------------------------------------------
        # Date of birth
        # -----------------------------------------------------

        raw_dob = self._find_value(
            cleaned_text,
            [
                r"(?:date\s*of\s*birth|dob|birth\s*date)"
                r"\s*[:\-]\s*([^\n]+)"
            ]
        )

        if raw_dob:
            result["date_of_birth"] = self._normalize_date(raw_dob)

        # -----------------------------------------------------
        # Search type
        # -----------------------------------------------------

        result["search_type"] = self._find_value(
            cleaned_text,
            [
                r"search\s*type\s*[:\-]\s*([^\n]+)",
                r"type\s*of\s*search\s*[:\-]\s*([^\n]+)"
            ]
        )

        # -----------------------------------------------------
        # State
        # -----------------------------------------------------

        state = self._find_value(
            cleaned_text,
            [
                r"state\s*[:\-]\s*([^\n]+)"
            ]
        )

        if state:
            result["state"] = self._normalize_state(state)

        # -----------------------------------------------------
        # County
        # -----------------------------------------------------

        result["county"] = self._find_value(
            cleaned_text,
            [
                r"county\s*[:\-]\s*([^\n]+)"
            ]
        )

        # -----------------------------------------------------
        # Source location
        # -----------------------------------------------------

        result["source_location"] = self._find_value(
            cleaned_text,
            [
                r"source\s*location\s*[:\-]\s*([^\n]+)",
                r"(?:court|courthouse|town\s*hall)"
                r"\s*[:\-]\s*([^\n]+)"
            ]
        )

        # -----------------------------------------------------
        # Special instructions
        # -----------------------------------------------------

        result["special_instructions"] = self._find_value(
            cleaned_text,
            [
                r"special\s*instructions?\s*[:\-]\s*([^\n]+)",
                r"instructions?\s*[:\-]\s*([^\n]+)",
                r"notes?\s*[:\-]\s*([^\n]+)"
            ]
        )

        return result

    # ---------------------------------------------------------
    # Parsing helpers
    # ---------------------------------------------------------

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Normalize extracted PDF text while preserving line breaks.
        """

        lines = []

        for line in text.splitlines():

            line = re.sub(
                r"[ \t]+",
                " ",
                line
            ).strip()

            if line:
                lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def _find_value(
        text: str,
        patterns: List[str]
    ) -> Optional[str]:
        """
        Find the first matching value from several regex patterns.
        """

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE
            )

            if match:
                value = match.group(1).strip()

                value = value.strip(
                    " \t\r\n:;-"
                )

                if value:
                    return value

        return None

    @staticmethod
    def _parse_full_name(full_name: str) -> Dict:
        """
        Parse a basic human name.

        Examples:
            John Smith
            John A Smith
            John Michael Smith
        """

        # Remove common accidental extra spaces
        parts = [
            part
            for part in full_name.strip().split()
            if part
        ]

        first_name = None
        middle_name = None
        last_name = None

        if len(parts) == 1:
            first_name = parts[0]

        elif len(parts) == 2:
            first_name = parts[0]
            last_name = parts[1]

        elif len(parts) >= 3:
            first_name = parts[0]
            last_name = parts[-1]
            middle_name = " ".join(parts[1:-1])

        return {
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name
        }

    @staticmethod
    def _normalize_date(value: str) -> Optional[str]:
        """
        Convert several common date formats to YYYY-MM-DD.
        """

        value = value.strip()

        # Remove text after a clearly separated note.
        value = value.split("|")[0].strip()

        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%y",
            "%d/%m/%y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y"
        ]

        for date_format in formats:

            try:
                parsed = datetime.strptime(
                    value,
                    date_format
                )

                return parsed.strftime(
                    "%Y-%m-%d"
                )

            except ValueError:
                continue

        # Try extracting a date from a longer string.
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{1,2}/\d{1,2}/\d{4}",
            r"\d{1,2}-\d{1,2}-\d{4}"
        ]

        for pattern in date_patterns:

            match = re.search(
                pattern,
                value
            )

            if match:
                return PDFParser._normalize_date(
                    match.group(0)
                )

        return None

    @staticmethod
    def _normalize_state(value: str) -> str:
        """
        Normalize common US state names to two-letter abbreviations.

        Unknown values are returned unchanged.
        """

        value = value.strip()

        states = {
            "alabama": "AL",
            "alaska": "AK",
            "arizona": "AZ",
            "arkansas": "AR",
            "california": "CA",
            "colorado": "CO",
            "connecticut": "CT",
            "delaware": "DE",
            "florida": "FL",
            "georgia": "GA",
            "hawaii": "HI",
            "idaho": "ID",
            "illinois": "IL",
            "indiana": "IN",
            "iowa": "IA",
            "kansas": "KS",
            "kentucky": "KY",
            "louisiana": "LA",
            "maine": "ME",
            "maryland": "MD",
            "massachusetts": "MA",
            "michigan": "MI",
            "minnesota": "MN",
            "mississippi": "MS",
            "missouri": "MO",
            "montana": "MT",
            "nebraska": "NE",
            "nevada": "NV",
            "new hampshire": "NH",
            "new jersey": "NJ",
            "new mexico": "NM",
            "new york": "NY",
            "north carolina": "NC",
            "north dakota": "ND",
            "ohio": "OH",
            "oklahoma": "OK",
            "oregon": "OR",
            "pennsylvania": "PA",
            "rhode island": "RI",
            "south carolina": "SC",
            "south dakota": "SD",
            "tennessee": "TN",
            "texas": "TX",
            "utah": "UT",
            "vermont": "VT",
            "virginia": "VA",
            "washington": "WA",
            "west virginia": "WV",
            "wisconsin": "WI",
            "wyoming": "WY",
            "district of columbia": "DC"
        }

        lowered = value.lower()

        if lowered in states:
            return states[lowered]

        if len(value) == 2:
            return value.upper()

        return value

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def _validate_result(
        self,
        result: Dict
    ) -> Dict:
        """
        Validate extracted data.
        """

        validation_errors = []

        for field in self.required_fields:

            value = result.get(field)

            if value is None or value == "":
                validation_errors.append(
                    f"Missing required field: {field}"
                )

        if result.get("date_of_birth"):

            try:
                datetime.strptime(
                    result["date_of_birth"],
                    "%Y-%m-%d"
                )

            except ValueError:
                validation_errors.append(
                    "Invalid date format for date_of_birth "
                    "(should be YYYY-MM-DD)"
                )

        result["validation_errors"] = (
            validation_errors
            if validation_errors
            else None
        )

        result["is_valid"] = (
            len(validation_errors) == 0
        )

        return result

    # ---------------------------------------------------------
    # Multiple PDFs
    # ---------------------------------------------------------

    def parse_multiple_pdfs(
        self,
        pdf_paths: List[str]
    ) -> List[Dict]:
        """
        Parse several PDF files.
        """

        results = []

        for pdf_path in pdf_paths:

            try:
                result = self.parse_pdf(
                    pdf_path
                )

                results.append(
                    result
                )

            except Exception as exc:

                logger.exception(
                    "Error parsing %s",
                    pdf_path
                )

                results.append(
                    {
                        "error": str(exc),
                        "success": False,
                        "is_valid": False,
                        "pdf_filename": os.path.basename(
                            pdf_path
                        )
                    }
                )

        return results


# ---------------------------------------------------------
# Standalone test
# ---------------------------------------------------------

def main():
    """
    Test the PDF parser against the first PDF found
    in temp/pdf_downloads.
    """

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

    parser = PDFParser(config)

    test_directory = os.path.join(
        project_root,
        "temp",
        "pdf_downloads"
    )

    os.makedirs(
        test_directory,
        exist_ok=True
    )

    pdf_files = [
        filename
        for filename in os.listdir(test_directory)
        if filename.lower().endswith(".pdf")
    ]

    if not pdf_files:
        print(
            "No PDF files found for testing.\n"
            f"Put a PDF inside:\n{test_directory}"
        )
        return

    pdf_path = os.path.join(
        test_directory,
        pdf_files[0]
    )

    result = parser.parse_pdf(
        pdf_path
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
