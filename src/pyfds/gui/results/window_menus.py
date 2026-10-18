"""Results window: menu bar."""
from __future__ import annotations

from PySide6.QtGui import QActionGroup

from pyfds.api.viz import model as vm


class ResultsWindowMenusMixin:
    # -- menus ------------------------------------------------------------------------------------------------------
    def _build_menus(self) -> None:
        mb = self.menuBar()
        v = self.viewer
        f = mb.addMenu("&File")
        self._act(f, "&New Results Visualization", lambda: (v.new(), self.sync(True)))
        self._act(f, "&Open Results Visualization...", self.open_visualization, "Ctrl+O")
        self._act(f, "Open &Results (.smv)...", self.open_results)
        self._act(f, "&Save Results Visualization", self.save, "Ctrl+S")
        self._act(f, "Save &As...", self.save_as)
        f.addSeparator()
        self._act(f, "&Load Results...", self.load_results)
        self._act(f, "&Unload FDS Results", lambda: (v.unload_results(), self.sync(True)))
        self._act(f, "Re&fresh Results", self.refresh, "F5")
        self._act(f, "Load &CSV File...", self.load_csv)
        f.addSeparator()
        self._act(f, "&Import Views...", self.import_views)
        self._act(f, "&Export Views...", self.export_views)
        self._act(f, "Export &Data (CSV)...", self.export_data)
        f.addSeparator()
        self._act(f, "Save &Screenshot...", self.screenshot, "Ctrl+P")
        self._act(f, "Save &Movie...", self.movie)
        self._act(f, "Save &360 Movie...", self.movie360)
        self._act(f, "&Record Movie (real time)...", self.record_start, "F9")
        self._act(f, "Pause / Resume Recording", self.record_pause_resume, "F10")
        self._act(f, "Stop Recording", self.record_stop, "Shift+F9")
        f.addSeparator()
        self._act(f, "&Close", self.close)

        vw = mb.addMenu("&View")
        for name, label in (("top", "&Top"), ("front", "&Front"), ("side", "&Side"), ("isometric", "&Reset Camera")):
            self._act(vw, label, lambda n=name: (v.standard_view(n), self._camera_changed()))
        vw.addSeparator()
        grp = QActionGroup(self)
        for proj in ("perspective", "orthogonal"):
            a = self._act(vw, proj.capitalize(), lambda p=proj: (v.set_projection(p), self._camera_changed()),
                          checkable=True, checked=v.camera.projection == proj)
            grp.addAction(a)
        nav = vw.addMenu("&Navigation Tool")
        g2 = QActionGroup(self)
        for tool in ("orbit", "pan", "zoom", "roam", "smokeview"):
            g2.addAction(self._act(nav, tool.capitalize(), lambda t=tool: v.set_navigation(t), checkable=True,
                                   checked=v.camera.navigation == tool))
        rm = vw.addMenu("Rendering &Mode")
        for m in vm.RENDER_MODES:
            self._act(rm, m.replace("_", " ").capitalize(), lambda x=m: (v.set_rendering_mode(x), self.sync()))
        gs = vw.addMenu("&Geometry Set")
        for g in vm.GEOMETRY_SETS:
            self._act(gs, g.replace("_", " ").upper() if g == "ge1" else g.replace("_", " ").title(),
                      lambda x=g: (v.set_geometry_set(x), self.sync(True)))
        vw.addSeparator()
        self._act(vw, "New &View...", self.new_view)
        self._act(vw, "New T&our...", self.new_tour)
        self._act(vw, "&Default View", lambda: (v.activate_view(None), self.sync(True)))
        self._act(vw, "Add &Section Box", lambda: (v.add_section_box(), self.sync(True)))
        self._act(vw, "Remove Section Box", lambda: (v.remove_section_box(), self.sync()))
        self._act(vw, "Set Section &Plane...", self.section_plane)
        vw.addSeparator()
        self._act(vw, "Show &Dimensions", lambda: (v.show_annotations(dimensions=not v.viz.show_dimensions), self.sync()),
                  checkable=True, checked=v.viz.show_dimensions)
        self._act(vw, "Show &Labels", lambda: (v.show_annotations(labels=not v.viz.show_labels), self.sync()),
                  checkable=True, checked=v.viz.show_labels)

        tl = mb.addMenu("&Tools")
        self._act(tl, "Add &Dimension...", self.add_dimension)
        self._act(tl, "Add &Label...", self.add_label)
        self._act(tl, "Add Tour &Keyframe at Current Time", lambda: (v.add_keyframe(), self.sync()))
        tl.addSeparator()
        self._act(tl, "&Time History Plot...", self.time_plot)
        self._act(tl, "Data&3D: Add Isosurface...", self.add_iso)

        pf = mb.addMenu("&Preferences")
        self._act(pf, "&FDS Preferences...", self.fds_prefs)
        self._act(pf, "&Colorbar...", self.colorbar_prefs)
        self._act(pf, "3D S&moke...", lambda: self._edit("3D Smoke", v.viz.smoke3d, v.set_smoke3d,
                                                          {"preset": vm.SMOKE_PRESETS, "fire_rendering": ("radiant", "volumetric")}))
        self._act(pf, "&Units...", lambda: self._edit("Units", v.viz.units, v.set_units, {
            "temperature": ("C", "F", "K"), "concentration": ("ppm", "fraction", "percent"), "mass_fraction": ("kg/kg", "g/kg")}))
        self._act(pf, "T&imelines...", lambda: self._edit("Timelines", v.viz.timelines, lambda **k: v.set_timelines(**k), {
            "display_format": ("regional", "iso8601"), "view_timeline": ("automatic", "custom")}))
        self._act(pf, "&General...", lambda: self._edit("General", v.viz.general, lambda **k: v.set_general(**k)))
        self._act(pf, "&Rendering...", self.rendering_prefs)
        self._act(pf, "Fl&oors...", self.floors)
        self._act(pf, "&Time Display...", self.time_display)
