"""PyFDS Command-Line Interface."""
from .main import main
import argparse
import sys


def validate_fds() -> None:
    """Backward-compat CLI entry point (v0.2.0): validate an FDS file."""
    ap = argparse.ArgumentParser(description="Validate an FDS file.")
    ap.add_argument("file", help="Path to the .fds file")
    args = ap.parse_args()

    from pyfds.api.controller import FdsApi
    api = FdsApi()
    try:
        api.load(args.file)
    except Exception as exc:
        print(f"Load error: {exc}")
        sys.exit(1)

    report = api.validation.validate()
    if not report.passed:
        print("Validation Errors:")
        for r in report.results:
            print(f" - {r.message}")
        sys.exit(1)
    print("Model valid.")


__all__ = ["main", "validate_fds"]
