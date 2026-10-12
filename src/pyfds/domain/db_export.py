"""
PyFDS Database Export
=====================
Export built-in material, surface, and fuel databases to JSON or CSV so
they can be used in GUIs, spreadsheets, or FDS pre-processing scripts.

Functions
---------
export_materials(filepath, fmt="json")
export_surfaces(filepath, fmt="json")
export_fuels(filepath, fmt="json")
export_all(dirpath, fmt="json", stem="pyfds_db")
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict


def _write_json(data: Any, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _write_csv(records: Dict[str, Dict[str, Any]], filepath: str) -> None:
    """Flatten a ``{name: {field: value}}`` dict to CSV rows."""
    if not records:
        Path(filepath).write_text("", encoding="utf-8")
        return
    # Collect all unique field names (preserve insertion order)
    field_set: Dict[str, bool] = {}
    for d in records.values():
        for k in d:
            field_set[k] = True
    fieldnames = ["name"] + [f for f in field_set if f != "name"]
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for name, d in records.items():
            row = {k: ("" if v is None else v) for k, v in d.items()}
            row["name"] = name
            writer.writerow(row)


def _check_fmt(fmt: str) -> None:
    if fmt not in ("json", "csv"):
        raise ValueError(f"Unknown format {fmt!r}. Choose 'json' or 'csv'.")


def export_materials(filepath: str, fmt: str = "json") -> None:
    """Export ``MATERIAL_PRESETS`` to *filepath* in *fmt* format."""
    _check_fmt(fmt)
    from pyfds.domain.material_presets import MATERIAL_PRESETS
    if fmt == "json":
        _write_json(MATERIAL_PRESETS, filepath)
    else:
        _write_csv(MATERIAL_PRESETS, filepath)


def export_surfaces(filepath: str, fmt: str = "json") -> None:
    """Export ``SURFACE_PRESETS`` to *filepath* in *fmt* format."""
    _check_fmt(fmt)
    from pyfds.domain.material_presets import SURFACE_PRESETS
    if fmt == "json":
        _write_json(SURFACE_PRESETS, filepath)
    else:
        _write_csv(SURFACE_PRESETS, filepath)


def export_fuels(filepath: str, fmt: str = "json") -> None:
    """Export ``FUEL_LIBRARY`` to *filepath* in *fmt* format."""
    _check_fmt(fmt)
    from pyfds.domain.reactions import FUEL_LIBRARY
    if fmt == "json":
        _write_json(FUEL_LIBRARY, filepath)
    else:
        _write_csv(FUEL_LIBRARY, filepath)


def export_all(
    dirpath: str,
    *,
    fmt: str = "json",
    stem: str = "pyfds_db",
) -> Dict[str, str]:
    """
    Export all three databases to *dirpath*.

    Creates the directory if it does not exist.

    Returns
    -------
    dict
        ``{"materials": path, "surfaces": path, "fuels": path}`` for each file
        written.
    """
    _check_fmt(fmt)
    Path(dirpath).mkdir(parents=True, exist_ok=True)
    out: Dict[str, str] = {}
    for db_name, fn in [
        ("materials", export_materials),
        ("surfaces",  export_surfaces),
        ("fuels",     export_fuels),
    ]:
        path = str(Path(dirpath) / f"{stem}_{db_name}.{fmt}")
        fn(path, fmt=fmt)
        out[db_name] = path
    return out
