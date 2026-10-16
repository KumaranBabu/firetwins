"""Tools and Help entries that used to say "Coming soon": Script Console, Tutorials, Check for Updates."""
from __future__ import annotations

from typing import Any

from pyfds.gui.script_console import ScriptConsoleDialog
from pyfds.gui.tutorials_dialog import TutorialsDialog
from pyfds.gui.update_dialog import UpdateDialog


class ActionsToolsExtraMixin:
    def _on_script_console(self) -> ScriptConsoleDialog:
        """A non-modal Python console with ``api`` and ``window`` (one per window, brought forward if open)."""
        dlg = getattr(self, "_script_console", None)
        if dlg is None:
            dlg = ScriptConsoleDialog(self.api, self, self)
            self._script_console = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def _on_tutorials(self) -> TutorialsDialog:
        dialog = TutorialsDialog(self)
        self._tutorials_dialog = dialog
        dialog.exec()
        return dialog

    def _on_check_updates(self) -> UpdateDialog:
        dialog = UpdateDialog(self.api, self)
        self._update_dialog = dialog
        dialog.exec()
        return dialog
