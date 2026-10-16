"""Menu construction: view, draw."""
from __future__ import annotations

from PySide6.QtGui import QActionGroup

from .shared import (
    _CAMERA_PRESETS,
    _DRAW_ACTIONS,
    _DRAW_TOOL_ACTIONS,
    _VISIBILITY_TOGGLES,
)


class MenusViewDrawMixin:
    def _build_view_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # VIEW MENU (16 items)
        # ════════════════════════════════════════════════════════════════════════
        view_menu = self.menuBar().addMenu("&View")

        # Which view is in front (PyroSim: Show 3D / 2D / Record View)
        view_menu.addAction("Show &3D View", self.show_model_tab)
        view_menu.addAction("Show &2D View", self.show_plan_tab)
        view_menu.addAction("Show Re&cord View", self.show_record_tab)
        view_menu.addSeparator()

        # View navigation
        self._reset_view_action = view_menu.addAction("&Reset View", self._on_reset_view)

        # Standard camera presets (existing, 7 items)
        views_submenu = view_menu.addMenu("&Standard Views")
        self._camera_preset_actions = {}
        for label, preset in _CAMERA_PRESETS:
            action = views_submenu.addAction(label, lambda checked=False, p=preset: self._on_camera_preset(p))
            self._camera_preset_actions[preset] = action

        view_menu.addSeparator()

        # Render modes (new and existing)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        self._render_menu_actions = {}
        for mode, label in (("wireframe", "&Wireframe Mode"), ("solid", "&Shaded Mode"),
                            ("outlines", "&Outlines Mode"), ("realistic", "&Realistic Mode")):
            action = view_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda _c=False, m=mode: self._on_render_mode(m))
            mode_group.addAction(action)
            self._render_menu_actions[mode] = action
        self._wireframe_action = self._render_menu_actions["wireframe"]
        view_menu.addAction("Save &Image...", self._on_save_view_image)

        view_menu.addSeparator()

        # Display toggles
        show_submenu = view_menu.addMenu("&Show/Hide")
        for label, flag in _VISIBILITY_TOGGLES:
            action = show_submenu.addAction(label)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(lambda checked, f=flag: self._on_toggle_visibility(f, checked))

        # Additional show/hide items (new)
        show_submenu.addSeparator()
        self._grid_action = show_submenu.addAction("&Grid")
        self._axes_action = show_submenu.addAction("&Axes")
        for action, handler in ((self._grid_action, self._on_toggle_grid), (self._axes_action, self._on_toggle_axes)):
            action.setCheckable(True)
            action.toggled.connect(handler)

        view_menu.addSeparator()

        # Section view (new)
        view_menu.addAction("Section &Box Around Selection", self._on_section_box_around_selection)
        view_menu.addAction("Reset Section Bo&x", self._on_reset_section_box)

        # Split view (new)
        split_submenu = view_menu.addMenu("&Split")
        split_submenu.addAction("Horizontal", self._on_placeholder_split_horizontal)
        split_submenu.addAction("Vertical", self._on_placeholder_split_vertical)
        split_submenu.addAction("Four-Way", self._on_placeholder_split_four_way)

        # Fullscreen (new)
        view_menu.addAction("&Fullscreen", self._on_toggle_fullscreen)

        view_menu.addSeparator()

        # Bookmarks (new) — in-memory (session-only) named camera states
        view_menu.addAction("Save &Bookmark...", self._on_save_bookmark)
        view_menu.addAction("Load &Bookmark...", self._on_load_bookmark)

        view_menu.addSeparator()

        # Theme (new)
        theme_submenu = view_menu.addMenu("&Theme")
        theme_submenu.addAction("&Light", lambda: self._on_theme_chosen("light"))
        theme_submenu.addAction("&Dark", lambda: self._on_theme_chosen("dark"))

        # Units (new)
        units_submenu = view_menu.addMenu("&Units")
        units_submenu.addAction("&Metric (m, kg, s)", self._on_units_metric)
        units_submenu.addAction("&Imperial (ft, lb, s)", self._on_units_imperial)


    def _build_draw_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # DRAW MENU (14 items) — Expanded from 4 to include primitive shapes
        # ════════════════════════════════════════════════════════════════════════
        draw_menu = self.menuBar().addMenu("&Draw")

        # Primitive shapes draw mode
        draw_group = QActionGroup(self)
        draw_group.setExclusive(True)
        self._draw_actions = {}

        # Basic drawing tools (existing)
        for label, tool_name in _DRAW_ACTIONS + _DRAW_TOOL_ACTIONS:
            action = draw_menu.addAction(label)
            action.setCheckable(True)
            draw_group.addAction(action)
            action.triggered.connect(lambda checked=False, t=tool_name: self._on_set_draw_mode(t))
            self._draw_actions[tool_name] = action

        draw_menu.addSeparator()

        # Additional primitive shapes (new) — dialog-driven, via api.geom
        # (NOT the box-footprint draw-mode pipeline: these have no natural
        # two-click XB footprint, and there is no "add_cylinder"/"add_sphere"/
        # "add_cone" agent tool for _on_box_footprint_picked to dispatch to).
        draw_menu.addAction("Draw &Cylinder...", self._on_draw_cylinder)
        draw_menu.addAction("Draw &Sphere...", self._on_draw_sphere)
        draw_menu.addAction("Draw C&one...", self._on_draw_cone)
        draw_menu.addAction("Draw &Pipe...", lambda: self._on_placeholder_geometry_primitive("Pipe"))
        draw_menu.addAction("Draw &Beam...", lambda: self._on_placeholder_geometry_primitive("Beam"))

        draw_menu.addSeparator()

        # Architectural elements (new) — no backend primitive yet
        for elem in ["Floor", "Ceiling", "Stair", "Door", "Window", "Ramp"]:
            draw_menu.addAction(f"Draw {elem}...", lambda checked=False, e=elem: self._on_placeholder_geometry_primitive(e))

        draw_menu.addSeparator()

        # Boolean operations (new)
        bool_submenu = draw_menu.addMenu("&Boolean Operations")
        bool_submenu.addAction("&Union", self._on_boolean_union)
        bool_submenu.addAction("&Difference", self._on_boolean_difference)
        bool_submenu.addAction("&Intersection", self._on_boolean_intersection)

        draw_menu.addSeparator()

        # Cancel draw mode
        draw_menu.addAction("&Cancel Draw Mode", self._on_cancel_draw_mode)
