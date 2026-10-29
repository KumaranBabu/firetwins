"""File > Import / Export entries that used to say "Coming soon" (plan step F1): Import FDS file / materials / devices /
scenarios / library, Export Scenario Definitions, Export and Import Configuration, and Run > Monitor Simulation.

Every import goes through ``api.clipboard.merge_file`` (one undo step; shared definitions are reused, other clashes
renamed) and ends with a summary of what happened, so nothing changes silently."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Optional, Sequence

from PySide6.QtWidgets import QFileDialog, QMessageBox

from pyfds.gui.library_dialog import LibraryDialog

_FDS_FILTER = "FDS or PyFDS files (*.fds *.pyfds);;All files (*)"
_MATERIAL_KINDS = ["materials", "ramps"]
_DEVICE_KINDS = ["devices", "controls", "props", "ramps"]


def merge_summary(r: Dict[str, Any]) -> str:
    """A short readable account of one merge result."""
    kinds = Counter(type(e).__name__ for e in r["added"])
    lines = ["Added: " + (", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) or "nothing")]
    if r["renamed"]:
        lines.append("Renamed to avoid a clash: " + ", ".join(f"{a} -> {b}" for a, b in r["renamed"].items()))
    if r["skipped"]:
        lines.append("Already in the model, reused: " + ", ".join(r["skipped"]))
    if r["warnings"]:
        lines.append(f"{len(r['warnings'])} warning(s) while reading, e.g. {r['warnings'][0]}")
    return "\n".join(lines)


class ActionsImportMixin:
    # -- merging files into the model ----------------------------------------------------------------------------------
    def _import_merge(self, title: str, categories: Optional[Sequence[str]], path: str = "") -> Optional[Dict[str, Any]]:
        path = path or QFileDialog.getOpenFileName(self, title, "", _FDS_FILTER)[0]
        if not path:
            return None
        try:
            result = self.api.clipboard.merge_file(path, categories)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, title, str(exc))
            return None
        self.explorer.refresh()
        self.statusBar().showMessage(f"{title}: {len(result['added'])} added from {path}", 8000)
        QMessageBox.information(self, title, merge_summary(result))
        return result

    def _on_import_fds(self, path: str = "") -> Optional[Dict[str, Any]]:
        """Add everything in an FDS or PyFDS file to the open project (it is not replaced)."""
        return self._import_merge("Import FDS File", None, path)

    def _on_import_materials(self, path: str = "") -> Optional[Dict[str, Any]]:
        return self._import_merge("Import Materials", _MATERIAL_KINDS, path)

    def _on_import_devices(self, path: str = "") -> Optional[Dict[str, Any]]:
        return self._import_merge("Import Devices", _DEVICE_KINDS, path)

    def _on_import_library(self) -> LibraryDialog:
        dialog = LibraryDialog(self.api, self)
        self._library_dialog = dialog
        dialog.exec()
        return dialog

    # -- scenarios -----------------------------------------------------------------------------------------------------------
    def _on_import_scenarios(self, path: str = "", overwrite: bool = False) -> Optional[Dict[str, Any]]:
        title = "Import Scenarios"
        path = path or QFileDialog.getOpenFileName(self, title, "", "Scenario definitions (*.json)")[0]
        if not path:
            return None
        try:
            r = self.api.scenarios.import_definitions(path, overwrite=overwrite)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, title, str(exc))
            return None
        self.explorer.refresh()
        text = f"Added {len(r['added'])}, replaced {len(r['replaced'])}, skipped {len(r['skipped'])} (already exist)."
        if r["missing"]:
            text += f"\n{len(r['missing'])} change(s) left out because the object is not in this model:\n  " + \
                "\n  ".join(r["missing"][:8])
        QMessageBox.information(self, title, text)
        return r

    def _on_import_scenarios_dialog(self) -> Optional[Dict[str, Any]]:
        return self._on_import_scenarios()

    def _on_export_scenario_definitions(self, path: str = "") -> int:
        title = "Export Scenario Definitions"
        if not self.api.scenarios.all():
            QMessageBox.information(self, title, "There are no scenarios to export.")
            return 0
        path = path or QFileDialog.getSaveFileName(self, title, "scenarios.json", "Scenario definitions (*.json)")[0]
        if not path:
            return 0
        n = self.api.scenarios.export_definitions(path)
        self.statusBar().showMessage(f"Wrote {n} scenario(s) to {path}", 6000)
        return n

    # -- configuration -------------------------------------------------------------------------------------------------------
    def _on_export_config(self, path: str = "") -> int:
        path = path or QFileDialog.getSaveFileName(self, "Export Configuration", "pyfds_config.json",
                                                   "Configuration (*.json)")[0]
        if not path:
            return 0
        n = self.api.preferences.export_config(path)
        self.statusBar().showMessage(f"Wrote {n} settings to {path}", 6000)
        return n

    def _on_import_config(self, path: str = "") -> Optional[Dict[str, Any]]:
        title = "Import Configuration"
        path = path or QFileDialog.getOpenFileName(self, title, "", "Configuration (*.json)")[0]
        if not path:
            return None
        try:
            r = self.api.preferences.import_config(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, title, str(exc))
            return None
        self._sync_shell_bars()
        text = f"Applied {len(r['applied'])} setting(s)."
        if r["rejected"]:
            text += "\nLeft alone: " + "; ".join(f"{k} ({why})" for k, why in r["rejected"].items())
        QMessageBox.information(self, title, text)
        return r

    # -- running ---------------------------------------------------------------------------------------------------------------
    def _on_monitor_simulation(self, output_dir: str = "") -> bool:
        """Watch the last (or a chosen) run: progress, step time and a link into the results."""
        from pathlib import Path
        out = output_dir or getattr(self, "_last_run_dir", None)
        if not out:
            QMessageBox.information(self, "Monitor Simulation", "Start a run first (Analysis > Run Simulation).")
            return False
        self.run_panel.watch(out, self.api.project.chid, self.api.project.params.t_end,
                             lambda: self.open_in_results(str(Path(out) / f"{self.api.project.chid}.smv")))
        self._show_messages(self.run_panel)
        return True
