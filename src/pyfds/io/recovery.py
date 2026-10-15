"""Backup-on-open and autosave recovery files (PRJ-03).

For a project file ``dir/name.pyfds``:

* the **backup** ``dir/name.~bak.pyfds`` is a copy of the file as it was when last opened;
* the **autosave** ``dir/~name.pyfds`` is a side file written periodically while the project has
  unsaved changes. The real file is never touched by autosave. Saving removes the autosave file.

An autosave that is newer than its project file means the last session ended without saving.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def backup_path(path) -> Path:
    p = Path(path)
    return p.with_name(p.stem + ".~bak" + p.suffix)


def is_side_file(path) -> bool:
    """Backup and autosave files are never themselves backed up when opened."""
    p = Path(path)
    return p.name.startswith("~") or p.stem.endswith(".~bak")


def autosave_path(path) -> Path:
    p = Path(path)
    return p.with_name("~" + p.name)


def make_backup(path) -> Optional[Path]:
    """Copy *path* to its backup file. Returns the backup path, or None when it could not be written
    (read-only folder, file missing) - a backup must never stop a file from opening."""
    src = Path(path)
    dst = backup_path(src)
    try:
        if not src.is_file():
            return None
        if dst.is_file() and dst.stat().st_size == src.stat().st_size and dst.read_bytes() == src.read_bytes():
            return dst
        shutil.copy2(src, dst)
        return dst
    except OSError as exc:
        logger.warning("Could not write backup for %s: %s", src, exc)
        return None


def write_autosave(project: Any, path) -> Path:
    """Write the project to the autosave side file for *path* (the real file is left alone)."""
    from pyfds.io.serializer import Serializer
    target = autosave_path(path)
    Serializer().save(project, str(target), autosave=True)
    return target


def discard_autosave(path) -> bool:
    a = autosave_path(path)
    try:
        if a.is_file():
            a.unlink()
            return True
    except OSError as exc:
        logger.warning("Could not remove %s: %s", a, exc)
    return False


def find_recovery(path) -> Optional[Dict[str, Any]]:
    """Info about an autosave newer than *path* (or whose project file is gone), else None."""
    p = Path(path)
    a = autosave_path(p)
    if not a.is_file():
        return None
    a_time = a.stat().st_mtime
    if p.is_file() and a_time <= p.stat().st_mtime:
        return None
    return {"autosave": str(a), "project": str(p), "saved_at": a_time, "project_exists": p.is_file()}
