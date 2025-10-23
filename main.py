import sys
from pathlib import Path
from normalize_contact import normalize_contacts


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_file>")
        return 1

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1

    output_file = input_path.with_name(f"normalized_{input_path.name}")
    success = normalize_contacts(str(input_path), str(output_file))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
