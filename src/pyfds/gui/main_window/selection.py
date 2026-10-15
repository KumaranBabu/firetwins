"""Small pure helpers for the main window (group naming). Transform maths lives in ``api.transform``."""
from __future__ import annotations


def _next_group_name(existing: set) -> str:
    n = 1
    while f"Group {n}" in existing:
        n += 1
    return f"Group {n}"
