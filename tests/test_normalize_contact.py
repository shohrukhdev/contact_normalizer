import csv
from pathlib import Path
import pytest

import normalize_contacts
from normalize_contacts import ContactNormalizer, normalize_contacts


def write_csv(path: Path, headers, rows, delimiter=";"):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(headers)
        w.writerows(rows)


@pytest.fixture
def normalizer(tmp_path):
    return ContactNormalizer(input_file=str(tmp_path / "in.csv"), output_file=str(tmp_path / "out.csv"))


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Leading '+' with noise should keep '+' and strip other junk
        ("+971 50 123 4567", "+971501234567"),
        ("+1(415)-555-2671", "+14155552671"),
        ("+44-20-7946-0958", "+442079460958"),
        ("+", None),  # '+' alone is not a number
        # Local UAE (starts with 0, 10 digits)
        ("0501234567", "+971501234567"),
        ("054-123-4567", "+971541234567"),
        ("0 58 123 4567", "+971581234567"),
        # Already UAE digits without '+'
        ("971501234567", "+971501234567"),
        ("971-50-123-4567", "+971501234567"),
        # Generic numbers without '+'
        ("4155552671", "+4155552671"),
        ("00123456789", "+00123456789"),
        # Length boundaries (8..15 digits)
        ("12345678", "+12345678"),
        ("1234567", None),             # too short
        ("1"*15, f"+{'1'*15}"),
        ("1"*16, None),                # too long
        # Empty / invalid inputs
        ("", None),
        (None, None),
        (12345, None),
    ],
)
def test_normalize_phone(normalizer, raw, expected):
    assert normalizer.normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        # ISO-like formats
        ("1990-02-01", "1990-02-01"),
        ("1990/02/01", "1990-02-01"),
        ("1990.02.01", "1990-02-01"),
        ("19900201", "1990-02-01"),
        # Month names
        ("01-Feb-1990", "1990-02-01"),
        ("01-Feb-90", "1990-02-01"),
        ("1 Feb 1990", "1990-02-01"),
        ("Feb 1 1990", "1990-02-01"),
        ("February 1, 1990", "1990-02-01"),
        ("1990 Feb 01", "1990-02-01"),
        # Ambiguous numeric: assume day-first unless impossible
        ("01/02/1990", "1990-02-01"),
        ("12/11/1990", "1990-11-12"),
        ("13/01/1990", "1990-01-13"),  # 13 forces day-first
        ("02/01/1990", "1990-01-02"),
        ("02-01-1990", "1990-01-02"),
        # Two-digit years with pivot
        ("01-02-00", "2000-02-01"),
        ("01-02-25", "2025-02-01"),
        ("01-02-99", "1999-02-01"),
        # Dots/slashes and two-digit years
        ("01.02.1990", "1990-02-01"),
        ("01/02/90", "1990-02-01"),
        # Invalid samples
        ("01-02-26", "1926-02-01"),
        ("32/01/1990", None),
        ("00/01/1990", None),
        ("", None),
        (None, None),
        (123, None),
        ("Feb 30 1990", None),
    ],
)
def test_normalize_date(normalizer, raw, expected):
    assert normalizer.normalize_date(raw) == expected


@pytest.mark.parametrize(
    "row,expected",
    [
        (
            {"id": "A1", "phone": "0501234567", "dob": "01/02/1990"},
            {"id": "A1", "phone": "+971501234567", "dob": "1990-02-01"},
        ),
        (
            {"ID": "B2", "Phone": "+1 (415) 555-2671", "DoB": "Feb 1, 1990"},
            {"id": "B2", "phone": "+14155552671", "dob": "1990-02-01"},
        ),
    ],
)
def test_normalize_row_success(normalizer, row, expected):
    assert normalizer.normalize_row(row) == expected


@pytest.mark.parametrize(
    "row,err_contains",
    [
        ({"phone": "0501234567", "dob": "01/02/1990"}, "Missing id"),
        ({"id": "X1", "phone": "", "dob": "01/02/1990"}, "Invalid phone"),
        ({"id": "X2", "phone": "0501234567", "dob": ""}, "Invalid date"),
    ],
)
def test_normalize_row_failures(normalizer, row, err_contains):
    with pytest.raises(ValueError) as e:
        normalizer.normalize_row(row)
    assert err_contains in str(e.value)


def test_process_success_and_output(tmp_path):
    input_file = tmp_path / "in.csv"
    output_file = tmp_path / "out.csv"

    headers = ["id", "phone", "dob"]
    rows = [
        ["A1", "0501234567", "01/02/1990"],           # OK
        ["A2", "+1 (415) 555-2671", "Feb 1 1990"],    # OK
        ["A3", "", "01/02/1990"],                     # invalid phone
        ["", "0501234567", "01/02/1990"],             # missing id
        ["A4", "0501234567", ""],                     # invalid date
    ]
    write_csv(input_file, headers, rows, delimiter=";")

    norm = ContactNormalizer(str(input_file), str(output_file))
    ok = norm.process()
    assert ok is True

    # Check counters
    assert norm.stats.total == 5
    assert norm.stats.normalized == 2
    assert norm.stats.skipped == 3
    assert len(norm.stats.errors) == 3

    # Verify written CSV content and header order
    with output_file.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter=normalize_contacts.CSV_DELIMITER)
        out_rows = list(r)
    assert r.fieldnames == ["id", "phone", "dob"]
    assert out_rows == [
        {"id": "A1", "phone": "+971501234567", "dob": "1990-02-01"},
        {"id": "A2", "phone": "+14155552671", "dob": "1990-02-01"},
    ]


def test_process_empty_or_no_headers(tmp_path, capsys):
    input_file = tmp_path / "in.csv"
    output_file = tmp_path / "out.csv"
    input_file.write_text("", encoding="utf-8")

    norm = ContactNormalizer(str(input_file), str(output_file))
    ok = norm.process()
    captured = capsys.readouterr()

    assert ok is False
    assert "CSV file is empty or has no headers" in captured.out
    assert output_file.exists()


def test_process_input_not_exists(tmp_path, capsys):
    input_file = tmp_path / "missing.csv"
    output_file = tmp_path / "out.csv"

    norm = ContactNormalizer(str(input_file), str(output_file))
    ok = norm.process()
    captured = capsys.readouterr()

    assert ok is False
    assert "Input file not found" in captured.out


def test_normalize_contacts_success(tmp_path, capsys):
    input_file = tmp_path / "data.csv"
    output_file = tmp_path / "normalized.csv"

    headers = ["id", "phone", "dob"]
    rows = [
        ["Z1", "0501234567", "01/02/1990"],
        ["Z2", "971501234567", "1990-02-01"],
    ]
    write_csv(input_file, headers, rows)

    ok = normalize_contacts(str(input_file), str(output_file))
    # Should always print a summary
    captured = capsys.readouterr()
    assert ok is True
    assert "NORMALIZATION SUMMARY" in captured.out

    with output_file.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter=";")
        out_rows = list(r)
    assert out_rows == [
        {"id": "Z1", "phone": "+971501234567", "dob": "1990-02-01"},
        {"id": "Z2", "phone": "+971501234567", "dob": "1990-02-01"},
    ]


def test_process_ignores_bom_and_uses_semicolon(tmp_path):
    input_file = tmp_path / "bom.csv"
    output_file = tmp_path / "out.csv"

    with input_file.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "phone", "dob"])
        w.writerow(["A1", "0501234567", "01/02/1990"])

    norm = ContactNormalizer(str(input_file), str(output_file))
    assert norm.process() is True

    with output_file.open("r", encoding="utf-8") as f:
        content = f.read().strip()
    assert content.splitlines()[0] == "id;phone;dob"
    assert "A1;+971501234567;1990-02-01" in content
