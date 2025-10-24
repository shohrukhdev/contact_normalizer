import os
import sys
from pathlib import Path
from normalize_contact import normalize_contacts


def parse_args(args: list[str] = None) -> tuple[Path, int | None]:
    """
    Get CLI arguments.

    Returns:
        (input_path, max_workers)
    """
    if len(args) < 2:
        print("Usage:\n"
              "  python main.py <input_file>\n"
              "  python main.py <input_file> multiprocess [<cores>]")
        sys.exit(1)

    input_path = Path(args[1])
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Default: single-process
    max_workers: int | None = None

    # Optional multiprocess flag
    if len(args) >= 3 and args[2].lower() == "multiprocess":
        if len(args) >= 4:
            try:
                requested = int(args[3])
                if requested <= 0:
                    raise ValueError
            except ValueError:
                print("Error: <cores> must be a positive integer")
                sys.exit(1)
            available = os.cpu_count() or 1
            max_workers = min(requested, available)
        else:
            # 0 means auto-detect physical/available cores in normalize_contact
            max_workers = 0

    return input_path, max_workers


def main() -> int:
    input_path, max_workers = parse_args(sys.argv)
    output_file = input_path.with_name(f"normalized_{input_path.name}")

    success = normalize_contacts(
        str(input_path),
        str(output_file),
        max_workers=max_workers if max_workers is not None else None)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
