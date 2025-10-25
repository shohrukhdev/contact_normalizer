import csv
from datetime import datetime
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple, Any
import os
import multiprocessing as mp
import time

CSV_DELIMITER = ';'
DEFAULT_MAX_WORKERS: int | None = None
DEFAULT_CHUNK_MULTIPLIER = 4


@dataclass
class NormalizationStats:
    """Lightweight counters for the run."""
    total: int = 0
    normalized: int = 0
    skipped: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def normalize_phone(phone: str) -> str | None:
    """
    Convert a phone number to E.164 if possible.

    Rules:
      - Keep a leading '+' if present, drop other non-digits
      - If it looks like a local UAE mobile (starts with 0 and has 10 digits),
        switch to +971 and drop the leading 0

    Args:
        phone (str): raw phone input

    Returns:
        str | None: E.164 number or None if invalid
    """
    if not phone or not isinstance(phone, str):
        return None

    # If it starts with +, keep it and strip everything else
    if phone.startswith("+"):
        digits = re.sub(r"[^0-9]", "", phone[1:])
        if not digits:
            return None
        # Basic E.164 length check
        if 8 <= len(digits) <= 15:
            return f"+{digits}"
        return None

    # No plus: strip non-digits
    digits = re.sub(r"[^0-9]", "", phone)
    if not digits:
        return None

    # Local UAE: 0XXXXXXXXX (10 digits) -> +971XXXXXXXX
    if digits.startswith("0") and len(digits) == 10:
        return f"+971{digits[1:]}"

    # Already has 971 country code without '+'
    if digits.startswith("971") and 8 <= len(digits) <= 15:
        return f"+{digits}"

    # Fallback: treat as international without '+'
    if 8 <= len(digits) <= 15:
        return f"+{digits}"

    return None


def normalize_date(date_str: str) -> str | None:
    """
    Parse a date into YYYY-MM-DD.

    Args:
        date_str (str): raw date input

    Returns:
        str | None: normalized date or None if invalid
    """
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip()

    formats_to_try = [
        # Full Year Formats (Y-m-d, Y/m/d, Y.m.d, Ymd)
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
        # Month name formats - these are unambiguous and stay
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
    ]

    for fmt in formats_to_try:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.year < 100:  # apply two-digit year rule
                dt = adjust_two_digit_year(dt)
            if dt > datetime.now():
                return None
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Last resort: try to infer order from numbers
    normalized_date = parse_ambiguous_date(date_str)
    if normalized_date and normalized_date > datetime.now():
        return None
    if not normalized_date:
        return None
    return normalized_date.strftime('%Y-%m-%d')


def parse_ambiguous_date(date_str: str) -> datetime | None:
    """
    Try to decode fuzzy numeric dates.
    Prefer day-first; if that fails or month > 12, try month-first.

    Args:
        date_str (str): raw input

    Returns:
        datetime | None
    """
    numbers = re.findall(r"\d+", date_str)

    if len(numbers) < 3:
        return None

    # Three parts we can shuffle into day/month/year
    part1, part2, part3 = int(numbers[0]), int(numbers[1]), int(numbers[2])

    # Pick the year spot:
    # - if the last looks like a year (>31 or >=1000), use it
    # - else if the first looks like a year, use that
    # - else use the middle if it’s clearly a year, otherwise fall back to the last
    if part3 >= 1000 or part3 > 31:
        year = part3
        d1, m1 = part1, part2  # DD/MM
        d2, m2 = part2, part1  # MM/DD
    elif part1 >= 1000 or part1 > 31:
        year = part1
        d1, m1 = part2, part3
        d2, m2 = part3, part2
    else:
        if part2 >= 1000:
            year = part2
            d1, m1 = part3, part1
            d2, m2 = part1, part3
        else:
            year = part3
            d1, m1 = part1, part2
            d2, m2 = part2, part1

    # Two-digit year pivot: 00–25 -> 2000–2025; 26–99 -> 1926–1999
    if year < 100:
        year = 2000 + year if year <= 25 else 1900 + year

    # Try day-first, then month-first
    day, month = d1, m1
    if 1 <= day <= 31 and 1 <= month <= 12:
        try:
            return datetime(year, month, day)
        except ValueError:
            pass

    day, month = d2, m2
    if 1 <= day <= 31 and 1 <= month <= 12:
        try:
            return datetime(year, month, day)
        except ValueError:
            pass

    return None


def adjust_two_digit_year(dt: datetime) -> datetime:
    """
    Expand two-digit years using the pivot rule:
    00–25 → 2000–2025, 26–99 → 1926–1999.
    """
    if dt.year <= 25:
        year = 2000 + dt.year
    else:
        year = 1900 + dt.year

    return datetime(year, dt.month, dt.day)


def normalize_row(row: dict) -> dict | None:
    """
    Normalize one CSV row.

    Args:
        row: a mapping with keys like id, phone, dob (case-insensitive)

    Returns:
        dict | None: normalized row or raises on validation error
    """
    # Downcase keys and trim values
    row_lower = {str(k).lower().strip(): (v.strip() if isinstance(v, str) else "") for k, v in row.items()}

    contact_id = row_lower.get('id', '').strip()
    phone = row_lower.get('phone', '').strip()
    dob = row_lower.get('dob', '').strip()

    if not contact_id:
        raise ValueError("Missing id")

    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        raise ValueError(f"Invalid phone: {phone}")

    normalized_dob = normalize_date(dob)
    if not normalized_dob:
        raise ValueError(f"Invalid date of birth: {dob}")

    return {
        'id': contact_id,
        'phone': normalized_phone,
        'dob': normalized_dob
    }


def worker_pack(args: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, str] | None, str | None]:
    seq, row = args
    try:
        normalized = normalize_row(row)
        return seq, normalized, None
    except Exception as e:
        return seq, None, f"Row {seq} (ID: {row.get('id', 'unknown')}): {e}"


class ContactNormalizer:
    """Normalize contacts loaded from a CSV file."""

    def __init__(self, input_file: str, output_file: str, max_workers: int | None = DEFAULT_MAX_WORKERS):
        """
        Set up paths and stats.

        Args:
            input_file (str): path to source CSV
            output_file (str): path to write results to
            max_workers (Optional[int]): None=single-process, 0=auto, N>0 explicit
        """
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.stats = NormalizationStats()
        self.max_workers = max_workers
        self.elapsed_seconds: float | None = None

    def _resolve_workers(self) -> int:
        """
        Determine worker count for multiprocessing mode.
        """
        if self.max_workers == 0:
            try:
                return max(1, len(os.sched_getaffinity(0)))
            except Exception:
                return max(1, os.cpu_count() or 1)
        if isinstance(self.max_workers, int) and self.max_workers > 0:
            available = os.cpu_count() or 1
            return max(1, min(self.max_workers, available))
        return 1

    def normalize_phone(self, phone: str) -> str | None:
        return normalize_phone(phone)

    def normalize_date(self, date_str: str) -> str | None:
        return normalize_date(date_str)

    def normalize_row(self, row: dict) -> dict | None:
        return normalize_row(row)

    def _process_single(self) -> bool:
        """
        Read the input CSV, normalize rows, and write the output.

        Returns:
            bool: True on success, False on failure
        """
        start = time.perf_counter()
        try:
            if not self.input_file.exists():
                print(f"Error: Input file not found: {self.input_file}", flush=True)
                return False

            # Ensure output folder exists
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            with (open(self.input_file, 'r', encoding='utf-8-sig', newline='') as infile,
                  open(self.output_file, 'w', encoding='utf-8', newline='') as outfile):

                reader = csv.DictReader(infile, delimiter=CSV_DELIMITER)

                if reader.fieldnames is None:
                    print("Error: CSV file is empty or has no headers", flush=True)
                    return False

                writer = csv.DictWriter(outfile, fieldnames=['id', 'phone', 'dob'], delimiter=CSV_DELIMITER)
                writer.writeheader()

                for idx, row in enumerate(reader, start=2):  # data starts after header line
                    self.stats.total += 1
                    try:
                        normalized_row = self.normalize_row(row)
                        writer.writerow(normalized_row)
                        self.stats.normalized += 1
                    except Exception as e:
                        self.stats.skipped += 1
                        row_lower = {str(k).lower().strip(): (v.strip() if isinstance(v, str) else "") for k, v in
                                     row.items()}
                        contact_id = row_lower.get('id', 'unknown')
                        self.stats.errors.append(f"Row {idx} (ID: {contact_id}): {e}")

            return True

        except Exception as e:
            print(f"Error: {str(e)}", flush=True)
            return False
        finally:
            self.elapsed_seconds = (time.perf_counter() - start)

    def _process_multiprocess(self) -> bool:
        """Multiprocessing streaming path with single writer and in-order output."""
        start = time.perf_counter()
        try:
            if not self.input_file.exists():
                print(f"Error: Input file not found: {self.input_file}", flush=True)
                return False

            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            workers = self._resolve_workers()
            print(f"Running with {workers} worker processes", flush=True)

            with open(self.input_file, 'r', encoding='utf-8-sig', newline='') as infile, \
                    open(self.output_file, 'w', encoding='utf-8', newline='') as outfile:

                reader = csv.DictReader(infile, delimiter=CSV_DELIMITER)
                if reader.fieldnames is None:
                    print("Error: CSV file is empty or has no headers", flush=True)
                    writer = csv.DictWriter(outfile, fieldnames=['id', 'phone', 'dob'], delimiter=CSV_DELIMITER)
                    writer.writeheader()
                    return False

                writer = csv.DictWriter(outfile, fieldnames=['id', 'phone', 'dob'], delimiter=CSV_DELIMITER)
                writer.writeheader()

                # Chunk size tuned by worker count to amortize IPC overhead
                chunk_size = max(256, workers * DEFAULT_CHUNK_MULTIPLIER * 256)

                def row_stream() -> Iterable[Tuple[int, dict[str, Any]]]:
                    for idx, row in enumerate(reader, start=2):  # 2 = first data line after header
                        yield idx, row

                next_to_write = 2
                buffer: dict[int, tuple[dict[str, str] | None, str | None]] = {}

                # Start pool (ensure fork-safe entry; Docker and Linux are fine; Windows uses spawn)
                with mp.Pool(processes=workers) as pool:
                    for seq, normalized, err in pool.imap(worker_pack, row_stream(), chunksize=chunk_size):
                        self.stats.total += 1
                        if err:
                            self.stats.skipped += 1
                            self.stats.errors.append(err)
                            buffer[seq] = (None, err)
                        else:
                            self.stats.normalized += 1
                            buffer[seq] = (normalized, None)

                        # Write any contiguous ready rows in order
                        while next_to_write in buffer:
                            item, _ = buffer.pop(next_to_write)
                            if item:
                                writer.writerow(item)
                            next_to_write += 1

                    # Safety drain (usually no-ops with imap)
                    while next_to_write in buffer:
                        item, _ = buffer.pop(next_to_write)
                        if item:
                            writer.writerow(item)
                        next_to_write += 1

            return True
        except Exception as e:
            print(f"Error: {str(e)}", flush=True)
            return False
        finally:
            self.elapsed_seconds = (time.perf_counter() - start)

    def process(self) -> bool:
        """
        Dispatch between single-process and multiprocess execution.
        """
        if self.max_workers is None:
            # Single-process explicitly requested (default)
            return self._process_single()
        else:
            # Multiprocess: auto or explicit workers
            return self._process_multiprocess()

    def print_summary(self) -> None:
        """Print a short run summary."""
        success_pct = (self.stats.normalized / self.stats.total * 100) if self.stats.total else 0.0
        print("\n" + "=" * 60)
        print("NORMALIZATION SUMMARY")
        print("=" * 60)
        print(f"Total rows processed: {self.stats.total}")
        print(f"Successfully normalized: {self.stats.normalized}")
        print(f"Rows skipped: {self.stats.skipped}")
        print(f"Success rate: {success_pct:.2f}%")
        if self.elapsed_seconds:
            minutes, seconds = divmod(self.elapsed_seconds, 60.0)
            print(f"Total time: {self.elapsed_seconds:.3f}s ({int(minutes)}m {seconds:05.2f}s)")

        if self.stats.errors:
            print("\nSkipped rows (with reasons):")
            for error in self.stats.errors:
                print(f"  - {error}")

        print("=" * 60 + "\n")


def normalize_contacts(
        input_file: str,
        output_file: str = "normalized_contacts.csv",
        max_workers: int | None = DEFAULT_MAX_WORKERS
) -> bool:
    """
    Convenience wrapper to run the normalizer and print a summary.

    Args:
        input_file: path to input CSV
        output_file: path to output CSV (default: normalized_contacts.csv)
        max_workers: maximum number of workers to use for multiprocessing (default: None, single-process)

    Returns:
        bool: True on success, False otherwise
    """
    normalizer = ContactNormalizer(input_file, output_file, max_workers=max_workers)
    success = normalizer.process()
    normalizer.print_summary()
    return success
