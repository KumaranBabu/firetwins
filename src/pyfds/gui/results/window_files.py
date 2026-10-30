"""Results window: open, save, load, export, screenshots and movies."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox

from ..busy import busy
from .forms import SettingsDialog

from .window_common import _SMV_FILTER, _VIZ_FILTER


class ResultsWindowFilesMixin:
    # -- file ------------------------------------------------------------------------------------------------------------
    def open_visualization(self) -> None:
        if p := self._ask_file(True, "Open Results Visualization", _VIZ_FILTER):
            with busy(self, "Opening the visualization"):
                self.viewer.open_visualization(p)
            self.sync(True)

    def open_results(self, smv: Optional[str] = None) -> None:
        if smv or (smv := self._ask_file(True, "Open Results", _SMV_FILTER)):
            with busy(self, "Opening results") as b:
                b.tick(Path(smv).name)
                self.viewer.open_results(smv)
            self.sync(True)

    def open_or_refresh(self, smv: Optional[str] = None) -> None:
        """Another program (the model editor) asks for *smv*: refresh it when it is the case already open, else open it;
        either way come to the front. Errors are shown, not raised, because nobody is waiting for an answer."""
        try:
            if smv and self.viewer.run is not None and Path(self.viewer.run.path).resolve() == Path(smv).resolve():
                self.refresh()
            elif smv:
                self.open_results(smv)
        except Exception as exc:
            QMessageBox.warning(self, "Open Results", f"Could not open {smv}:\n{exc}")
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()

    def load_results(self) -> None:
        if p := self._ask_file(True, "Load Results", _SMV_FILTER):
            with busy(self, "Loading results") as b:
                b.tick(Path(p).name)
                self.viewer.load_results(p)
            self.sync(True)

    def save(self) -> None:
        if not self.viewer.path:
            return self.save_as()
        self.viewer.save()
        self.sync()

    def save_as(self) -> None:
        if p := self._ask_file(False, "Save Results Visualization", _VIZ_FILTER, self.viewer.path or ""):
            self.viewer.save(p)
            self.sync()

    def refresh(self) -> None:
        with busy(self, "Refreshing results"):
            info = self.viewer.refresh()
        self.sync(info["reloaded"])
        self.statusBar().showMessage(f"Refreshed: {info['records']} new frame record(s)")

    def load_csv(self) -> None:
        if p := self._ask_file(True, "Load CSV File", "CSV files (*.csv);;All files (*)"):
            try:
                self.viewer.load_csv(p)
            except ValueError as exc:                       # unknown layout: ask for the header rows
                dlg = SettingsDialog("CSV layout", __import__("pyfds.api.viz", fromlist=["csvload"]).csvload.guess_type(p), self,
                                     hide=("path", "csv_type"), note=f"{exc}\nDescribe the header rows (1-based; 0 = none).")
                if dlg.exec():
                    self.viewer.load_csv(p, **dlg.values())
            self.sync(True)

    def import_views(self) -> None:
        if p := self._ask_file(True, "Import Views", "Views (*.json *.pyfdsv);;All files (*)"):
            self.viewer.import_views(p)
            self.sync(True)

    def export_views(self) -> None:
        if p := self._ask_file(False, "Export Views", "Views (*.json)"):
            self.viewer.export_views(p)

    def export_data(self) -> None:
        ids = list(self.viewer.csv_series())
        if not ids:
            raise ValueError("no time series are loaded: use File > Load CSV File, or add a Data3D point")
        pick, ok = QInputDialog.getItem(self, "Export Data", "Series", ids, 0, False)
        if ok and (p := self._ask_file(False, "Export Data", "CSV (*.csv);;Tab separated (*.tsv)")):
            n = self.viewer.export_data([pick], p, tab_separated=p.lower().endswith(".tsv"))
            self.statusBar().showMessage(f"Wrote {n} rows to {p}")

    def screenshot(self) -> None:
        from .dialogs import ScreenshotDialog
        d = ScreenshotDialog(self.viewer, self, (self.view.width(), self.view.height()))
        if d.exec():
            shots = d.shots()
            with busy(self, "Saving images") as b:
                done = self.viewer.render_screenshots(shots, _ticking(self.view.make_renderer(self.viewer), b, len(shots),
                                                                      "Image"), d.size())
            self.statusBar().showMessage(f"Saved {len(done)} image(s)")

    def movie(self) -> None:
        from .dialogs import MovieDialog
        if self.viewer.playback is None:
            raise ValueError("nothing animated is active: switch on a slice, smoke or particles first")
        d = MovieDialog(self.viewer, self, (min(self.view.width(), 1920), min(self.view.height(), 1080)))
        if d.exec():
            plan = d.plan()
            with busy(self, "Rendering the movie") as b:
                res = self.viewer.render_movie(plan, _ticking(self.view.make_renderer(self.viewer), b, len(plan.times)),
                                               d.view.currentText())
            QMessageBox.information(self, "Movie", f"{res['frames']} frames -> {res['path']}" if res["encoded"] else
                                    f"No video encoder found; the {res['frames']} frames were kept in {res['frames_dir']}")

    def movie360(self) -> None:
        from .dialogs import MovieDialog
        from .scene_adapter import make_panorama_renderer
        if self.viewer.playback is None:
            raise ValueError("nothing animated is active: switch on a slice, smoke or particles first")
        d = MovieDialog(self.viewer, self, panorama=True)
        d.path.setText("movie360.mp4")
        if d.exec():
            plan = d.plan()
            with busy(self, "Rendering the 360 movie") as b:
                res = self.viewer.render_movie(plan, _ticking(make_panorama_renderer(self.viewer), b, len(plan.times)),
                                               d.view.currentText())
            QMessageBox.information(self, "360 Movie", f"{res['frames']} frames -> {res['path']}" if res["encoded"] else
                                    f"No video encoder found; the {res['frames']} frames were kept in {res['frames_dir']}")


def _ticking(renderer, b, total: int, what: str = "Frame"):
    """*renderer* that moves the hourglass on and counts each picture it draws ("Frame 3 of 90"); the last count
    stays up while the frames are joined into the movie."""
    count = [0]

    def draw(*args, **kwargs):
        count[0] += 1
        b.tick(f"{what} {count[0]} of {total}" + (" - joining the frames" if what == "Frame" and count[0] == total else ""))
        return renderer(*args, **kwargs)
    return draw
