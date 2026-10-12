"""Fortran record helpers."""
from __future__ import annotations

import struct

from pyfds.core.exceptions import FdsBinaryError


def _read_record(fh) -> bytes:
    """
    Read one Fortran unformatted sequential record.

    Format: [int32 length] [data bytes] [int32 length]
    Raises ``FdsBinaryError`` on mismatch or EOF.
    """
    len_bytes = fh.read(4)
    if len(len_bytes) < 4:
        raise EOFError("Fortran record: unexpected EOF reading leading marker")
    length = struct.unpack("<i", len_bytes)[0]
    data = fh.read(length)
    if len(data) < length:
        raise EOFError(f"Fortran record: expected {length} bytes, got {len(data)}")
    trail = fh.read(4)
    if len(trail) < 4:
        raise EOFError("Fortran record: unexpected EOF reading trailing marker")
    trail_len = struct.unpack("<i", trail)[0]
    if trail_len != length:
        raise FdsBinaryError(
            filepath=getattr(fh, "name", "?"),
            offset=fh.tell(),
            message=f"Fortran record length mismatch: {length} vs {trail_len}",
        )
    return data


def _read_string_record(fh) -> str:
    """Read a Fortran string record, stripped of whitespace."""
    return _read_record(fh).decode("ascii", errors="replace").strip()


def _skip_string_records(fh, n: int) -> None:
    """Skip *n* Fortran string records (used to consume binary file headers)."""
    for _ in range(n):
        _read_record(fh)
