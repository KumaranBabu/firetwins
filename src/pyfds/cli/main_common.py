"""Console output helpers for the command line."""
from __future__ import annotations

import sys


def _print_error(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def _print_ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _print_warn(msg: str) -> None:
    print(f"  ⚠  {msg}")
