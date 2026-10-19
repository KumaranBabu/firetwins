"""Results window: views, sections, annotations, plots, preferences."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QMessageBox, QPushButton

from .forms import SettingsDialog


class ResultsWindowToolsMixin:
    # -- views / tools -----------------------------------------------------------------------------------------------
    def new_view(self) -> None:
        name, ok = QInputDialog.getText(self, "New View", "Name")
        if ok:
            if self.view.interactive:                       # record what the user is looking at
                self.viewer.set_camera(self.view.adapter.read_camera(self.viewer.camera))
            self.viewer.new_view(name or None)
            self.sync(True)

    def new_tour(self) -> None:
        name, ok = QInputDialog.getText(self, "New Tour", "Name")
        if ok:
            self.viewer.new_tour(name or None)
            self.sync(True)

    def section_plane(self) -> None:
        plane, ok = QInputDialog.getItem(self, "Section plane", "Plane", ["x_min", "x_max", "y_min", "y_max", "z_min", "z_max"], 0, False)
        if ok:
            val, ok2 = QInputDialog.getDouble(self, "Section plane", "Position (m)", 0.0, -1e6, 1e6, 3)
            if ok2:
                if not self._has_section():
                    self.viewer.add_section_box()
                self.viewer.set_section_plane(plane, val)
                self.sync(True)

    def _has_section(self) -> bool:
        from pyfds.api.viz import views as vw
        return vw.active_section(self.viewer.viz) is not None

    def add_dimension(self) -> None:
        text, ok = QInputDialog.getText(self, "Dimension", "Two points  x1,y1,z1  x2,y2,z2")
        if ok:
            nums = [float(s) for s in text.replace(",", " ").split()]
            if len(nums) != 6:
                raise ValueError("give six numbers: x1 y1 z1 x2 y2 z2")
            self.viewer.add_dimension(nums[:3], nums[3:])
            self.sync()

    def add_label(self) -> None:
        text, ok = QInputDialog.getText(self, "Label", "Text")
        if ok and text:
            pt, ok2 = QInputDialog.getText(self, "Label", "Anchor point  x,y,z")
            if ok2:
                nums = [float(s) for s in pt.replace(",", " ").split()]
                self.viewer.add_label(text, nums)
                self.sync()

    def add_iso(self) -> None:
        groups = [n for n in self.viewer.tree.walk() if any(c.kind in ("slice3d", "plot3d") for c in n.leaves()) and n.kind == "group"
                  and n.children and any(ch.kind == "group" and ch.label in ("Points", "Slices", "Isosurfaces") for ch in n.children)]
        if not groups:
            raise ValueError("this run has no 3D Slices or Plot3D quantities")
        pick, ok = QInputDialog.getItem(self, "Data3D", "Quantity", [g.id for g in groups], 0, False)
        if ok:
            val, ok2 = QInputDialog.getDouble(self, "Data3D", "Isosurface value", 100.0, -1e9, 1e9, 3)
            if ok2:
                self.viewer.add_data3d_isosurface(pick, val)
                self.sync(True)

    def time_plot(self) -> None:
        from .plots import TimePlotDialog
        dlg = TimePlotDialog(self.viewer, self)
        self._plot = dlg
        dlg.show()

    # -- preferences -------------------------------------------------------------------------------------------------
    def fds_prefs(self) -> None:
        self._edit("FDS Preferences", self.viewer.viz.fds, lambda **k: self.viewer.set_fds_preferences(**k),
                   hide=("colorbars", "obscure_types"))

    def save_my_defaults(self) -> None:
        path = self.viewer.save_user_defaults()
        QMessageBox.information(self, "My Defaults", f"New results visualizations will start from these preferences.\n\n{path}")

    def apply_my_defaults(self) -> None:
        if self.viewer.load_user_defaults():
            self.sync()
        else:
            QMessageBox.information(self, "My Defaults", "No defaults saved yet: use Preferences > Save as My Defaults first.")

    def forget_my_defaults(self) -> None:
        self.viewer.clear_user_defaults()

    def colorbar_prefs(self) -> None:
        qs = [q for q, _, _ in self.viewer.colorbars()] or list({l.quantity for l in self.viewer.tree.leaves() if l.quantity})
        if not qs:
            raise ValueError("no quantities to set a colorbar for: load results first")
        q, ok = QInputDialog.getItem(self, "Colorbar", "Quantity", qs, 0, False)
        if ok:
            from matplotlib import colormaps
            self._edit(f"Colorbar - {q}", self.viewer.viz.fds.colorbar(q), lambda **k: self.viewer.set_colorbar(q, **k),
                       {"colormap": sorted(colormaps)[:60] if False else ("turbo", "viridis", "jet", "rainbow", "hot", "coolwarm",
                                                                         "gray", "plasma", "inferno"),
                        "color_source": ("colormap", "constant"),
                        "opacity_source": ("constant", "gradient", "feather_below", "feather_above")})

    def rendering_prefs(self) -> None:
        """Preferences > Rendering: every option, the two presets, and a note on which options take effect."""
        from .quality import NOTE
        choices = {"antialiasing": ("disabled", "smaa_1x", "smaa_2tx", "msaa_2", "msaa_4", "msaa_8", "msaa_16"),
                   "slice_renderer": ("hardware", "compatibility"),
                   "data3d_slice_renderer": ("hardware", "compatibility", "disabled"),
                   "smoke_renderer": ("hardware", "compatibility", "smokeview"),
                   "data3d_renderer": ("hardware", "compatibility", "disabled")}
        dlg = SettingsDialog("Rendering", self.viewer.viz.rendering, self, choices, note=NOTE)
        row = QHBoxLayout()
        for label, preset in (("Max Quality", "max_quality"), ("Max Compatibility", "max_compatibility")):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, p=preset: (self._try(lambda: self.viewer.set_rendering(preset=p)), dlg.reject(), self.sync()))
            row.addWidget(b)
        dlg.layout().insertLayout(1, row)
        if dlg.exec() and (vals := dlg.values()):
            self._try(lambda: self.viewer.set_rendering(**vals), "Rendering")
            self.sync()

    def floors(self) -> None:
        text, ok = QInputDialog.getText(self, "Floors", "Z of each floor, metres (comma separated)",
                                        text=", ".join(str(z) for z in self.viewer.viz.floors.floors))
        if ok:
            levels = [float(s) for s in text.replace(",", " ").split()]
            self.viewer.set_floors(levels)
            self._edit("Floor layout", self.viewer.viz.floors, lambda **k: self.viewer.set_floor_layout(**k),
                       {"layout": ("vertical", "horizontal")}, hide=("floors", "visible"))

    def time_display(self) -> None:
        mode, ok = QInputDialog.getItem(self, "Time display", "Show", ["none", "time", "date_time"],
                                        ["none", "time", "date_time"].index(self.viewer.viz.time_display), False)
        if ok:
            self.viewer.set_time_display(mode)
            self.sync()
