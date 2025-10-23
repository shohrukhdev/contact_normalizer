import csv
from datetime import datetime
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

CSV_DELIMITER = ';'


@dataclass
class NormalizationStats:
    """Statistics of normalization."""
    total: int = 0
    normalized: int = 0
    skipped: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class ContactNormalizer:
    """Normalizes contacts from csv file."""

    def __init__(self, input_file: str, output_file: str):
        """
        Initialize the normalizer.
        Args:
            input_file(str): input file path
            output_file(str): output file path
        """
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.stats = NormalizationStats()

    def normalize_phone(self, phone: str) -> str | None:
        """
        Normalize phone number.

        Rules:
            - Remove all non-digit characters (except initial +)
            - If number is local starts with 0 then it's UAE(+971) drop the leading 0
        Args:
            phone(str): phone number to normalize
        Returns:
            str|None: normalized E.164 phone number or None if the phone number is invalid
        """
        if not phone or not isinstance(phone, str):
            return None

        # Keep leading +, strip other non-digits
        if phone.startswith("+"):
            digits = re.sub(r"[^0-9]", "", phone[1:])
            if not digits:
                return None
            # Basic E.164 length sanity check for phone number
            if 8 <= len(digits) <= 15:
                return f"+{digits}"
            return None

        # No leading +: strip all non-digits
        digits = re.sub(r"[^0-9]", "", phone)
        if not digits:
            return None

        # Local UAE rule: starts with 0 and has 10 digits (e.g., 05XXXXXXXX)
        if digits.startswith("0") and len(digits) == 10:
            return f"+971{digits[1:]}"

        # Already includes UAE country code like 9715..., normalize to +971...
        if digits.startswith("971") and 8 <= len(digits) <= 15:
            return f"+{digits}"

        if 8 <= len(digits) <= 15:
            return f"+{digits}"

        return None

    def normalize_date(self, date_str: str) -> str | None:
        """
        Parse date string to ISO 8601 format(YYYY-MM-DD).

        Args:
            date_str(str): date string to normalize.

        Returns:
            formatted date string or None if the date string is invalid.
        """
        if not date_str or not isinstance(date_str, str):
            return None
        date_str = date_str.strip()

        formats_to_try = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%Y%m%d",
            # month name formats
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%d %b %Y",
            "%d %B %Y",
            "%b-%d-%Y",
            "%B-%d-%Y",
            "%b %d %Y",
            "%B %d %Y",
            "%b %d, %Y",
            "%B %d, %Y",
            "%d-%b-%y",
            "%d-%B-%y",
            "%d %b %y",
            "%d.%b.%Y",
            "%d.%B.%Y",
            "%d/%b/%y",
            "%d/%B/%y",
            "%Y-%b-%d",
            "%Y %b %d",
            "%m.%d.%Y",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%m-%d-%y",
            "%m/%d/%y",
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d-%m-%y",
            "%d/%m/%y",
        ]

        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.year < 100:  # apply two digit year rule
                    dt = self._adjust_two_digit_year(dt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return self._parse_ambiguous_date(date_str)

    def _parse_ambiguous_date(self, date_str: str) -> str | None:
        """
        Parse ambiguous date string.
        assume day-first unless the month > 12 implies.
        Args:
            date_str(str): date string to normalize.
        Returns:
            formatted date string or None if the date string is invalid.
        """
        numbers = re.findall(r"\d+", date_str)

        if len(numbers) < 3:  # can't be a date
            return None

        # Get day, month, year candidates
        part1, part2, part3 = int(numbers[0]), int(numbers[1]), int(numbers[2])

        if part3 > 31:  # usually longest number on the last, so most likely year
            year = part3
            day_candidate1, month_candidate1 = part1, part2
            day_candidate2, month_candidate2 = part2, part1
        elif part1 > 31:
            year = part1
            day_candidate1, month_candidate1 = part2, part3
            day_candidate2, month_candidate2 = part3, part2
        else:
            year = part2
            day_candidate1, month_candidate1 = part3, part1
            day_candidate2, month_candidate2 = part1, part3

        if year < 100:
            if year <= 25:
                year += 2000
            else:
                year += 1900

        # Try DD/MM/YYYY first (day-first assumption)
        day, month = day_candidate1, month_candidate1
        if 1 <= day <= 31 and 1 <= month <= 12:
            try:
                dt = datetime(year, month, day)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass

        # If that failed or month > 12, try MM/DD/YYYY
        day, month = day_candidate2, month_candidate2
        if 1 <= day <= 31 and 1 <= month <= 12:
            try:
                dt = datetime(year, month, day)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass

        return None

    def _adjust_two_digit_year(self, dt: datetime) -> datetime:
        """
        Adjust two-digit year according to the pivot rule.

        00-25 → 2000-2025
        26-99 → 1926-1999
        """
        if dt.year <= 25:
            year = 2000 + dt.year
        else:
            year = 1900 + dt.year

        return datetime(year, dt.month, dt.day)

    def normalize_row(self, row: dict) -> dict | None:
        """
        Normalize a single contact row.

        Args:
            row: Dictionary representing a CSV row with keys: id, phone, dob

        Returns:
            Normalized row dictionary or None if normalization failed
        """
        # Get values (case-insensitive)
        row_lower = {str(k).lower().strip(): (v.strip() if isinstance(v, str) else "") for k, v in row.items()}

        contact_id = row_lower.get('id', '').strip()
        phone = row_lower.get('phone', '').strip()
        dob = row_lower.get('dob', '').strip()

        # ID is required
        if not contact_id:
            raise ValueError("Missing id")

        # Normalize phone
        normalized_phone = self.normalize_phone(phone)
        if not normalized_phone:
            raise ValueError(f"Invalid phone: {phone}")

        # Normalize date
        normalized_dob = self.normalize_date(dob)
        if not normalized_dob:
            raise ValueError(f"Invalid date: {dob}")

        return {
            'id': contact_id,
            'phone': normalized_phone,
            'dob': normalized_dob
        }

    def process(self) -> bool:
        """
        Process the input CSV file and write normalized output.

        Returns:
            True if processing was successful, False otherwise
        """
        try:
            # Check if input file exists
            if not self.input_file.exists():
                print(f"Error: Input file not found: {self.input_file}", flush=True)
                return False

            # Create output directory if it doesn't exist
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            # Read and process CSV
            normalized_rows: List[dict[str, str | None]] = []

            with open(self.input_file, 'r', encoding='utf-8-sig', newline='') as infile:
                # Use semicolon as delimiter as per the requirements
                reader = csv.DictReader(infile, delimiter=CSV_DELIMITER)

                if reader.fieldnames is None:
                    print("Error: CSV file is empty or has no headers", flush=True)
                    return False

                for idx, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
                    self.stats.total += 1
                    try:
                        normalized_row = self.normalize_row(row)
                        normalized_rows.append(normalized_row)
                        self.stats.normalized += 1
                    except Exception as e:
                        self.stats.skipped += 1
                        row_lower = {str(k).lower().strip(): (v.strip() if isinstance(v, str) else "") for k, v in
                                     row.items()}
                        contact_id = row_lower.get('id', 'unknown')
                        self.stats.errors.append(f"Row {idx} (ID: {contact_id}): {e}")

            # Write normalized data
            with open(self.output_file, 'w', encoding='utf-8', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=['id', 'phone', 'dob'], delimiter=CSV_DELIMITER)
                writer.writeheader()
                if normalized_rows:
                    writer.writerows(normalized_rows)

            return True

        except Exception as e:
            print(f"Error: {str(e)}", flush=True)
            return False

    def print_summary(self) -> None:
        """Print a short summary of the normalization process."""
        success_pct = (self.stats.normalized / self.stats.total * 100) if self.stats.total else 0.0
        print("\n" + "=" * 60)
        print("NORMALIZATION SUMMARY")
        print("=" * 60)
        print(f"Total rows processed: {self.stats.total}")
        print(f"Successfully normalized: {self.stats.normalized}")
        print(f"Rows skipped: {self.stats.skipped}")
        print(f"Success rate: {success_pct:.2f}%")

        if self.stats.errors:
            print("\nSkipped rows (with reasons):")
            for error in self.stats.errors:
                print(f"  - {error}")

        print("=" * 60 + "\n")


def normalize_contacts(
        input_file: str, output_file: str = "normalized_contacts.csv"
) -> bool:
    """
    Main function to normalize contacts from a CSV file.

    Args:
        input_file: Path to the input CSV file
        output_file: Path to the output CSV file (default: normalized_contacts.csv)

    Returns:
        True if successful, False otherwise
    """
    normalizer = ContactNormalizer(input_file, output_file)
    success = normalizer.process()
    normalizer.print_summary()
    return success

