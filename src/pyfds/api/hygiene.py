"""Project hygiene: ``api.hygiene`` (UX-18, PRJ-03, PRJ-04, PRJ-07, new-model defaults).

Write protection, backup and autosave recovery, "Remove All Objects", and the catalogue of
things a new PyroSim model starts with.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Collections that hold physical model objects; what "Remove All Objects" clears by default.
OBJECT_KINDS = ("obstructions", "vents", "holes", "geoms", "devices", "inits", "texts")

RESERVED_SURFACES = ("INERT", "ADIABATIC", "OPEN", "MIRROR", "HVAC", "PERIODIC", "PERIODIC FLOW ONLY")
DEFAULT_SPECIES = ("AIR", "NITROGEN", "OXYGEN", "CARBON DIOXIDE", "WATER VAPOR", "PRODUCTS",
                   "CARBON MONOXIDE", "SOOT", "HYDROGEN CYANIDE")
DEFAULT_PARTICLES = ("Tracer", "Water")
DEFAULT_VIEW = "Default"


class HygieneManager:
    def __init__(self, api) -> None:
        self._api = api

    # -- write protection (UX-18, PRJ-04) -----------------------------------------------
    @property
    def write_protected(self) -> bool:
        return self._api.project.editor.write_protected

    def set_write_protection(self, on: bool) -> bool:
        """Refuse to save over the file this project was opened from. Saving under another name makes an
        ordinary, unprotected copy. The flag is saved with the project."""
        self._api.project.editor.write_protected = bool(on)
        self._api.project.notify_global("WRITE_PROTECTION_CHANGED", bool(on))
        return self.write_protected

    # -- backup and recovery (PRJ-03) -----------------------------------------------------
    def backup_file(self, path: str) -> Optional[str]:
        from pyfds.io.recovery import backup_path
        p = backup_path(path)
        return str(p) if p.is_file() else None

    def restore_backup(self, path: str) -> str:
        """Load the backup copy made when *path* was last opened."""
        b = self.backup_file(path)
        if b is None:
            raise FileNotFoundError(f"no backup for {path}")
        self._api.load(b)
        self._api.project.source_path = str(Path(path).resolve())
        return b

    def recovery_available(self, path: str) -> Optional[Dict[str, Any]]:
        """Info about an autosave newer than *path*, or None."""
        from pyfds.io.recovery import find_recovery
        return find_recovery(path)

    def recover(self, path: str) -> Dict[str, Any]:
        """Load the autosave of *path* into the API. The project then belongs to *path* again, so saving
        writes the recovered work to the real file and removes the autosave."""
        info = self.recovery_available(path)
        if info is None:
            raise FileNotFoundError(f"nothing to recover for {path}")
        self._api.load(info["autosave"])
        self._api.project.source_path = str(Path(path).resolve())
        return info

    def discard_recovery(self, path: str) -> bool:
        from pyfds.io.recovery import discard_autosave
        return discard_autosave(path)

    # -- Remove All Objects (PRJ-07) --------------------------------------------------------
    def remove_all_objects(self, kinds: Optional[Iterable[str]] = None) -> Dict[str, int]:
        """Delete every object of the given collections (default: obstructions, vents, holes, geometry,
        devices, init regions, texts) as ONE undo step. Meshes, surfaces, materials and settings stay
        unless you name them. Returns how many were removed per collection."""
        from pyfds.automation.commands import RemoveEntityCommand
        valid = set(self._api.project._TYPE_MAP.values())
        kinds = tuple(kinds) if kinds is not None else OBJECT_KINDS
        bad = [k for k in kinds if k not in valid]
        if bad:
            raise KeyError(f"unknown kind(s): {', '.join(bad)}")
        counts: Dict[str, int] = {}
        with self._api.history.transaction("remove all objects"):
            for kind in kinds:
                items = list(getattr(self._api.project, kind))
                for e in items:
                    self._api.history.execute(RemoveEntityCommand(self._api.project, e))
                if items:
                    counts[kind] = len(items)
        return counts

    # -- what a new model starts with (B8 parity) -----------------------------------------
    def model_defaults(self) -> Dict[str, Any]:
        """What PyroSim lists in a new model's navigation tree. These are catalogue entries, not records:
        FDS already knows the reserved surfaces and its background species, and writing nine ``&SPEC``
        lines would change the physics, so none of them is added to the project."""
        return {"reserved_surfaces": list(RESERVED_SURFACES), "species": list(DEFAULT_SPECIES),
                "particle_classes": list(DEFAULT_PARTICLES), "view": DEFAULT_VIEW}

    def ensure_default_view(self) -> str:
        """Make sure the project has the 'Default' saved view (the current camera)."""
        if DEFAULT_VIEW not in self._api.project.editor.views:
            self._api.views.save_viewpoint(DEFAULT_VIEW)
        return DEFAULT_VIEW
