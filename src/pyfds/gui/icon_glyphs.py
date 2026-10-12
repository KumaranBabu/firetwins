"""The picture data for ``pyfds.gui.icons``: one small flat SVG per glyph, coloured by the task it belongs to.

Every glyph is drawn on a 24 x 24 grid. ``@c`` is the task colour, ``@d`` a darker and ``@l`` a lighter shade of it; a glyph may
also use fixed colours where the real thing has one (a red flame, a blue water drop, a red-green-blue axis triad).
"""
from __future__ import annotations

from typing import Dict, Tuple

# task -> main colour
TASK_COLORS: Dict[str, str] = {
    "file": "#3f6fb5",       # project files, import / export
    "edit": "#6b7a8f",       # edit, select, transform
    "view": "#5e5bc4",       # camera, display, navigation
    "geometry": "#1e88e5",   # meshes, obstructions, vents, drawing
    "physics": "#ef8a00",    # surfaces, materials, reactions, ramps
    "fire": "#e5383b",       # flames and heat
    "device": "#2e9e57",     # sensors and detectors
    "output": "#9c3fb5",     # slices, boundary files, isosurfaces
    "hvac": "#00897b",       # ducts, fans
    "run": "#2e9e2e",        # run and check
    "result": "#0097a7",     # results and plots
    "library": "#8d6e63",    # library, database, reports
    "annotate": "#d81b60",   # dimensions, labels, tours
    "time": "#546e7a",       # time and playback
    "info": "#1976d2",       # help
    "warn": "#f2a900",       # warnings
}

# glyph key -> (task, svg body)
GLYPHS: Dict[str, Tuple[str, str]] = {
    # -- files ---------------------------------------------------------------------------------
    "new": ("file", '<path d="M6 2h8l5 5v15H6z" fill="@l"/><path d="M14 2v5h5z" fill="@d"/><path d="M12.5 11v7M9 14.5h7" stroke="@c" stroke-width="2.2" stroke-linecap="round"/>'),
    "open": ("file", '<path d="M2 6a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v1H2z" fill="@d"/><path d="M2 9h21l-2.2 10a2 2 0 0 1-2 1.5H4a2 2 0 0 1-2-2z" fill="@c"/>'),
    "save": ("file", '<rect x="3" y="3" width="18" height="18" rx="2.5" fill="@c"/><rect x="7" y="3" width="10" height="6.5" fill="@l"/><rect x="14" y="4.2" width="2" height="4" fill="@d"/><rect x="6.5" y="13" width="11" height="8" rx="1" fill="#fff"/>'),
    "saveas": ("file", '<rect x="2.5" y="3" width="16" height="16" rx="2.5" fill="@c"/><rect x="6" y="3" width="9" height="5.5" fill="@l"/><rect x="5.5" y="12" width="9" height="7" rx="1" fill="#fff"/><path d="M13 22l1-4 7-7 3 3-7 7z" fill="#f2a900"/><path d="M21 11l3 3" stroke="#d4503a" stroke-width="2"/>'),
    "import": ("file", '<path d="M3 15v5h18v-5" fill="none" stroke="@d" stroke-width="2.4" stroke-linejoin="round"/><path d="M12 3v11M7.5 10 12 14.5 16.5 10" fill="none" stroke="@c" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "export": ("file", '<path d="M3 15v5h18v-5" fill="none" stroke="@d" stroke-width="2.4" stroke-linejoin="round"/><path d="M12 15V4M7.5 8 12 3.5 16.5 8" fill="none" stroke="@c" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "print": ("file", '<rect x="6" y="3" width="12" height="6" fill="@l"/><rect x="3" y="9" width="18" height="8" rx="2" fill="@c"/><rect x="6" y="14" width="12" height="7" fill="#fff" stroke="@d" stroke-width="1.2"/><circle cx="17.5" cy="11.8" r="1" fill="#f2a900"/>'),
    "settings": ("file", '<g fill="@c"><rect x="10.3" y="1.5" width="3.4" height="5" rx="1"/><rect x="10.3" y="17.5" width="3.4" height="5" rx="1"/><rect x="1.5" y="10.3" width="5" height="3.4" rx="1"/><rect x="17.5" y="10.3" width="5" height="3.4" rx="1"/><rect x="10.3" y="1.5" width="3.4" height="5" rx="1" transform="rotate(45 12 12)"/><rect x="10.3" y="17.5" width="3.4" height="5" rx="1" transform="rotate(45 12 12)"/><rect x="1.5" y="10.3" width="5" height="3.4" rx="1" transform="rotate(45 12 12)"/><rect x="17.5" y="10.3" width="5" height="3.4" rx="1" transform="rotate(45 12 12)"/></g><circle cx="12" cy="12" r="6.8" fill="@c"/><circle cx="12" cy="12" r="3" fill="@l"/>'),
    "exit": ("file", '<path d="M4 3h9v4h-2V5H6v14h5v-2h2v4H4z" fill="@d"/><path d="M11 11h6V7.5l5 4.5-5 4.5V13h-6z" fill="#e5383b"/>'),
    "close": ("file", '<circle cx="12" cy="12" r="10" fill="#e5383b"/><path d="M8 8l8 8M16 8l-8 8" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>'),
    "recent": ("file", '<circle cx="12" cy="12" r="9.5" fill="@l"/><path d="M12 6.5V12l4 2.5" fill="none" stroke="@d" stroke-width="2.2" stroke-linecap="round"/>'),
    "load": ("file", '<path d="M3 15v5h18v-5" fill="none" stroke="@d" stroke-width="2.4" stroke-linejoin="round"/><path d="M12 3v11M7.5 10 12 14.5 16.5 10" fill="none" stroke="#2e9e57" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "unload": ("file", '<path d="M12 3 4 12h16z" fill="@c"/><rect x="4" y="15" width="16" height="4" rx="1" fill="@d"/>'),
    "refresh": ("file", '<path d="M19 12a7 7 0 1 1-2.2-5.1" fill="none" stroke="@c" stroke-width="2.6" stroke-linecap="round"/><path d="M20.5 3.5V9H15z" fill="@d"/>'),
    # -- edit ---------------------------------------------------------------------------------
    "undo": ("edit", '<path d="M8 7H4v4" fill="none" stroke="@d" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M4.5 10.5C6.5 6.5 14 5 18 9c3 3 1 9-4 10" fill="none" stroke="@c" stroke-width="2.6" stroke-linecap="round"/>'),
    "redo": ("edit", '<path d="M16 7h4v4" fill="none" stroke="@d" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M19.5 10.5C17.5 6.5 10 5 6 9c-3 3-1 9 4 10" fill="none" stroke="@c" stroke-width="2.6" stroke-linecap="round"/>'),
    "cut": ("edit", '<circle cx="7" cy="18" r="3.2" fill="none" stroke="#e5383b" stroke-width="2"/><circle cx="17" cy="18" r="3.2" fill="none" stroke="#e5383b" stroke-width="2"/><path d="M8.5 15.2 18 3M15.5 15.2 6 3" stroke="@c" stroke-width="2.4" stroke-linecap="round"/>'),
    "copy": ("edit", '<rect x="8" y="8" width="13" height="13" rx="2" fill="@c"/><path d="M5 16H4a1.5 1.5 0 0 1-1.5-1.5V4A1.5 1.5 0 0 1 4 2.5h10.5A1.5 1.5 0 0 1 16 4v1" fill="none" stroke="@d" stroke-width="2"/>'),
    "paste": ("edit", '<rect x="4" y="4" width="16" height="18" rx="2" fill="@c"/><rect x="8" y="2" width="8" height="5" rx="1.5" fill="@d"/><rect x="7" y="10" width="10" height="9" rx="1" fill="#fff"/><path d="M9 13h6M9 16h4" stroke="@l" stroke-width="1.4"/>'),
    "delete": ("edit", '<path d="M5 7h14l-1.2 14H6.2z" fill="#e5383b"/><rect x="3" y="4.5" width="18" height="2.6" rx="1" fill="@d"/><rect x="9" y="2" width="6" height="3" rx="1" fill="@d"/><path d="M9.5 10v8M14.5 10v8" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>'),
    "duplicate": ("edit", '<rect x="3" y="7" width="12" height="12" rx="2" fill="@l"/><rect x="9" y="3" width="12" height="12" rx="2" fill="@c"/><path d="M15 6v6M12 9h6" stroke="#fff" stroke-width="2" stroke-linecap="round"/>'),
    "properties": ("edit", '<rect x="3" y="3" width="18" height="18" rx="2.5" fill="@l"/><path d="M6.5 8h11M6.5 12h11M6.5 16h7" stroke="@d" stroke-width="2" stroke-linecap="round"/><circle cx="17.5" cy="16" r="3.5" fill="#f2a900"/>'),
    "find": ("edit", '<circle cx="10" cy="10" r="6.5" fill="@l" stroke="@c" stroke-width="2.4"/><path d="M15 15l6 6" stroke="@d" stroke-width="3.2" stroke-linecap="round"/>'),
    "selectall": ("edit", '<rect x="3.5" y="3.5" width="17" height="17" rx="2" fill="@l" stroke="@c" stroke-width="2" stroke-dasharray="3 2.2"/><path d="M8 12.5l3 3 5-6" fill="none" stroke="@d" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'),
    "filter": ("edit", '<path d="M3 4h18l-7 9v6l-4 2v-8z" fill="@c"/><path d="M5.5 5.8h13" stroke="@l" stroke-width="1.6"/>'),
    "group": ("edit", '<rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="none" stroke="@c" stroke-width="2" stroke-dasharray="3 2.4"/><rect x="6" y="6" width="7" height="7" rx="1" fill="@c"/><rect x="11" y="11" width="7" height="7" rx="1" fill="@d"/>'),
    "ungroup": ("edit", '<rect x="3" y="3" width="8" height="8" rx="1.5" fill="@c"/><rect x="13" y="13" width="8" height="8" rx="1.5" fill="@d"/><path d="M14 8h6M17 5v6M4 17h6" stroke="@l" stroke-width="1.8" stroke-linecap="round"/>'),
    "move": ("edit", '<path d="M12 2l3.5 4h-7zM12 22l-3.5-4h7zM2 12l4-3.5v7zM22 12l-4 3.5v-7z" fill="@c"/><path d="M12 6v12M6 12h12" stroke="@d" stroke-width="2.2"/>'),
    "rotate": ("edit", '<path d="M19.5 12a7.5 7.5 0 1 1-2.6-5.7" fill="none" stroke="@c" stroke-width="2.8" stroke-linecap="round"/><path d="M21 3v6.5h-6.5z" fill="@d"/><circle cx="12" cy="12" r="1.8" fill="#f2a900"/>'),
    "scale": ("edit", '<rect x="3" y="11" width="10" height="10" rx="1.5" fill="@l"/><path d="M12 12 20 4M14 4h6v6" fill="none" stroke="@c" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'),
    "mirror": ("edit", '<path d="M12 2v20" stroke="@d" stroke-width="2" stroke-dasharray="2.5 2"/><path d="M10 5 3 19h7z" fill="@c"/><path d="M14 5l7 14h-7z" fill="@l"/>'),
    "snap": ("edit", '<path d="M5 4h5v9a2 2 0 0 0 4 0V4h5v9a7 7 0 0 1-14 0z" fill="@c"/><rect x="5" y="4" width="5" height="4.5" fill="#e5383b"/><rect x="14" y="4" width="5" height="4.5" fill="#1e88e5"/>'),
    # -- view ------------------------------------------------------------------------------------
    "resetview": ("view", '<path d="M3 11 12 3l9 8v10h-6v-6H9v6H3z" fill="@c"/><path d="M12 3l9 8H3z" fill="@d"/>'),
    "viewcube": ("view", '<path d="M12 2.5 21 7v10l-9 4.5L3 17V7z" fill="@c"/><path d="M12 2.5 21 7l-9 4.5L3 7z" fill="@l"/><path d="M3 7l9 4.5v10L3 17z" fill="@d"/><path d="M12 11.5 21 7" stroke="#fff" stroke-width=".8"/>'),
    "wireframe": ("view", '<path d="M12 2.5 21 7v10l-9 4.5L3 17V7zM3 7l9 4.5L21 7M12 11.5v10" fill="none" stroke="@c" stroke-width="2" stroke-linejoin="round"/>'),
    "shaded": ("view", '<path d="M12 2.5 21 7v10l-9 4.5L3 17V7z" fill="@c"/><path d="M12 2.5 21 7l-9 4.5L3 7z" fill="@l"/><path d="M3 7l9 4.5v10L3 17z" fill="@d"/>'),
    "realistic": ("view", '<circle cx="12" cy="12" r="9.5" fill="@c"/><ellipse cx="9" cy="8.5" rx="4" ry="3" fill="#fff" opacity=".55"/><path d="M5 17a9.5 9.5 0 0 0 14-5 9 9 0 0 1-14 5z" fill="@d"/>'),
    "eye": ("view", '<path d="M1.5 12S5.5 5 12 5s10.5 7 10.5 7-4 7-10.5 7S1.5 12 1.5 12z" fill="#fff" stroke="@c" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="@c"/><circle cx="13.2" cy="10.8" r="1.2" fill="#fff"/>'),
    "grid": ("view", '<path d="M3 20 8 5h13l-5 15z" fill="@l"/><path d="M5.5 12.5h13M4.3 16.2h13M10.5 5l-4.3 15M15.8 5l-2.6 15" stroke="@c" stroke-width="1.6"/>'),
    "axes": ("view", '<path d="M5 19 19 19" stroke="#e5383b" stroke-width="2.6" stroke-linecap="round"/><path d="M5 19V5" stroke="#2e9e2e" stroke-width="2.6" stroke-linecap="round"/><path d="M5 19 12 12.5" stroke="#1e88e5" stroke-width="2.6" stroke-linecap="round"/><path d="M21 19l-3-2v4zM5 3l-2 3h4zM14 10.5l-.5 3.5-3-2.5z" fill="#555"/>'),
    "section": ("view", '<path d="M12 2.5 21 7v10l-9 4.5L3 17V7z" fill="@l"/><path d="M5 20 2 14 15 8l7 3-8 9z" fill="#e5383b" opacity=".75"/><path d="M12 2.5 21 7v10l-9 4.5L3 17V7z" fill="none" stroke="@c" stroke-width="1.6"/>'),
    "split": ("view", '<rect x="2.5" y="3.5" width="19" height="17" rx="2" fill="@l" stroke="@c" stroke-width="2"/><path d="M12 3.5v17M2.5 12h19" stroke="@c" stroke-width="2"/>'),
    "fullscreen": ("view", '<path d="M3 9V3h6M15 3h6v6M21 15v6h-6M9 21H3v-6" fill="none" stroke="@c" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/><rect x="8" y="8" width="8" height="8" rx="1" fill="@l"/>'),
    "bookmark": ("view", '<path d="M6 2.5h12v19l-6-5-6 5z" fill="@c"/><path d="M6 2.5h12v5H6z" fill="@d"/>'),
    "theme": ("view", '<circle cx="12" cy="12" r="9.5" fill="#fff" stroke="@c" stroke-width="2"/><path d="M12 2.5a9.5 9.5 0 0 1 0 19z" fill="@c"/>'),
    "units": ("view", '<rect x="2" y="8" width="20" height="8" rx="1.5" fill="#ffca28"/><path d="M6 8v4M10 8v3M14 8v4M18 8v3" stroke="@d" stroke-width="1.6"/>'),
    "camera": ("view", '<path d="M2.5 8a2 2 0 0 1 2-2H7l1.5-2.5h7L17 6h2.5a2 2 0 0 1 2 2v10.5a2 2 0 0 1-2 2h-15a2 2 0 0 1-2-2z" fill="@c"/><circle cx="12" cy="13" r="4.8" fill="#fff"/><circle cx="12" cy="13" r="3" fill="@d"/><circle cx="18.2" cy="9.2" r="1" fill="#f2a900"/>'),
    "orbit": ("view", '<ellipse cx="12" cy="12" rx="10" ry="4.5" fill="none" stroke="@c" stroke-width="2.2" transform="rotate(-25 12 12)"/><circle cx="12" cy="12" r="4.5" fill="@d"/><circle cx="20" cy="8" r="2" fill="#f2a900"/>'),
    "pan": ("view", '<path d="M12 2l3.5 4h-7zM12 22l-3.5-4h7zM2 12l4-3.5v7zM22 12l-4 3.5v-7z" fill="@c"/><circle cx="12" cy="12" r="3.2" fill="@d"/>'),
    "zoom": ("view", '<circle cx="10" cy="10" r="6.5" fill="@l" stroke="@c" stroke-width="2.4"/><path d="M15 15l6 6" stroke="@d" stroke-width="3.2" stroke-linecap="round"/><path d="M7 10h6M10 7v6" stroke="@d" stroke-width="1.8" stroke-linecap="round"/>'),
    "roam": ("view", '<path d="M12 2.5C8 2.5 5.5 5.5 5.5 9c0 4.5 6.5 12.5 6.5 12.5S18.5 13.5 18.5 9C18.5 5.5 16 2.5 12 2.5z" fill="@c"/><circle cx="12" cy="9" r="3" fill="#fff"/>'),
    "ortho": ("view", '<rect x="4" y="5" width="16" height="14" fill="@l" stroke="@c" stroke-width="2"/><path d="M4 5 9 9.5h11M9 9.5V19" fill="none" stroke="@d" stroke-width="1.6"/>'),
    "viewtop": ("view", '<rect x="3.5" y="3.5" width="17" height="17" rx="1.5" fill="@c"/><path d="M7 7h10v10H7z" fill="@l"/>'),
    "viewfront": ("view", '<rect x="3.5" y="5" width="17" height="14" rx="1.5" fill="@c"/><path d="M3.5 5 7 2.5h14L20.5 5" fill="@l"/>'),
    "viewside": ("view", '<path d="M3 6 14 3v14L3 20z" fill="@d"/><path d="M14 3l7 2.5v14L14 17z" fill="@c"/>'),
    # -- geometry ----------------------------------------------------------------------------------
    "box": ("geometry", '<path d="M12 2.5 21 7l-9 4.5L3 7z" fill="@l"/><path d="M3 7l9 4.5v10L3 17z" fill="@d"/><path d="M21 7l-9 4.5v10l9-4.5z" fill="@c"/>'),
    "mesh": ("geometry", '<rect x="3" y="3" width="18" height="18" rx="2" fill="@l"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18" stroke="@c" stroke-width="1.7"/><rect x="3" y="3" width="18" height="18" rx="2" fill="none" stroke="@c" stroke-width="2.2"/>'),
    "wall": ("geometry", '<rect x="2.5" y="4" width="19" height="16" rx="1.5" fill="#d9774f"/><path d="M2.5 9.3h19M2.5 14.7h19M8.8 4v5.3M15.2 9.3v5.4M8.8 14.7V20" stroke="#fff" stroke-width="1.5"/>'),
    "vent": ("geometry", '<rect x="3" y="3" width="5" height="18" rx="1" fill="@d"/><path d="M10 8h6V4.5l6 7.5-6 7.5V16h-6z" fill="#f2a900"/>'),
    "hole": ("geometry", '<path d="M5.5 21V9a6.5 6.5 0 0 1 13 0v12z" fill="@c"/><path d="M8.5 21V9.5a3.5 3.5 0 0 1 7 0V21z" fill="#fff"/><path d="M2.5 21h19" stroke="@d" stroke-width="2"/>'),
    "door": ("geometry", '<path d="M6 21V3.5h12V21z" fill="@c"/><path d="M6 21V3.5l6 1.8v14.6z" fill="@d"/><circle cx="15.5" cy="12.5" r="1.3" fill="#ffca28"/><path d="M3 21h18" stroke="@d" stroke-width="2"/>'),
    "room": ("geometry", '<path d="M2.5 9 12 3l9.5 6v11.5h-19z" fill="@l"/><path d="M2.5 9 12 3l9.5 6" fill="none" stroke="@c" stroke-width="2.2"/><rect x="9.5" y="12.5" width="5" height="8" fill="@c"/><rect x="16" y="11.5" width="3.5" height="3.5" fill="#6ec6ff"/>'),
    "cylinder": ("geometry", '<path d="M4 6v12a8 3.2 0 0 0 16 0V6z" fill="@c"/><ellipse cx="12" cy="6" rx="8" ry="3.2" fill="@l"/>'),
    "sphere": ("geometry", '<circle cx="12" cy="12" r="9.5" fill="@c"/><ellipse cx="9" cy="8.5" rx="3.6" ry="2.6" fill="#fff" opacity=".55"/>'),
    "cone": ("geometry", '<path d="M12 2.5 4 18a8 3.2 0 0 0 16 0z" fill="@c"/><path d="M12 2.5 4 18a8 3.2 0 0 0 8 3.2z" fill="@d"/>'),
    "pipe": ("geometry", '<rect x="2" y="8" width="20" height="8" fill="@c"/><ellipse cx="3" cy="12" rx="2.2" ry="4" fill="@d"/><ellipse cx="21" cy="12" rx="2.2" ry="4" fill="@l"/><ellipse cx="21" cy="12" rx="1" ry="2.2" fill="#fff"/>'),
    "beam": ("geometry", '<path d="M3 8h18v3H14v7h-4v-7H3z" fill="@c"/><path d="M3 8h18v1.2H3z" fill="@l"/>'),
    "geom": ("geometry", '<path d="M3 19 12 4l9 15z" fill="@l" stroke="@c" stroke-width="2" stroke-linejoin="round"/><path d="M12 4v15M7.5 11.5h9" stroke="@c" stroke-width="1.5"/>'),
    "union": ("geometry", '<circle cx="9" cy="12" r="6.5" fill="@c"/><circle cx="15" cy="12" r="6.5" fill="@c"/>'),
    "difference": ("geometry", '<circle cx="9" cy="12" r="6.5" fill="@c"/><circle cx="15" cy="12" r="6.5" fill="#fff" stroke="@d" stroke-width="1.8"/>'),
    "intersection": ("geometry", '<circle cx="9" cy="12" r="6.5" fill="@l" stroke="@c" stroke-width="1.8"/><circle cx="15" cy="12" r="6.5" fill="@l" stroke="@c" stroke-width="1.8"/><path d="M12 6.7a6.5 6.5 0 0 1 0 10.6 6.5 6.5 0 0 1 0-10.6z" fill="@d"/>'),
    "voxel": ("geometry", '<g fill="@c"><rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="13" width="8" height="8" rx="1"/></g><g fill="@l"><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/></g>'),
    "cancel": ("geometry", '<circle cx="12" cy="12" r="9.5" fill="none" stroke="#e5383b" stroke-width="2.4"/><path d="M5.5 18.5 18.5 5.5" stroke="#e5383b" stroke-width="2.4"/>'),
    "init": ("geometry", '<rect x="3.5" y="3.5" width="17" height="17" rx="2" fill="@l" stroke="@c" stroke-width="2" stroke-dasharray="3 2.4"/><circle cx="12" cy="12" r="3.6" fill="#ef8a00"/>'),
    "floors": ("geometry", '<path d="M2 9.5 12 4.5l10 5-10 5z" fill="@l"/><path d="M2 13.5l10 5 10-5" fill="none" stroke="@c" stroke-width="2.4" stroke-linejoin="round"/><path d="M2 17.5l10 5 10-5" fill="none" stroke="@d" stroke-width="2.4" stroke-linejoin="round"/>'),
    "scenario": ("geometry", '<path d="M5 3v18" stroke="@d" stroke-width="2.4" stroke-linecap="round"/><path d="M6 4h13l-3.5 4.2L19 12.5H6z" fill="@c"/>'),
    "folder": ("geometry", '<path d="M2 6a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v1H2z" fill="@d"/><path d="M2 9.5h20V18a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z" fill="@c"/>'),
    # -- physics -----------------------------------------------------------------------------------
    "surface": ("physics", '<rect x="3" y="3" width="18" height="18" rx="2.5" fill="@l"/><path d="M3 15 15 3h6L3 21z" fill="@c"/><path d="M12 21 21 12v6a3 3 0 0 1-3 3z" fill="@d"/>'),
    "material": ("physics", '<path d="M12 3 22 8l-10 5L2 8z" fill="@l"/><path d="M2 12l10 5 10-5" fill="none" stroke="@c" stroke-width="2.6" stroke-linejoin="round"/><path d="M2 16.2l10 5 10-5" fill="none" stroke="@d" stroke-width="2.6" stroke-linejoin="round"/>'),
    "reaction": ("physics", '<path d="M6.5 7.5 12 16.5M17.5 7.5 12 16.5M6.5 7.5h11" stroke="@d" stroke-width="2"/><circle cx="6.5" cy="7.5" r="3.4" fill="#e5383b"/><circle cx="17.5" cy="7.5" r="3.4" fill="#1e88e5"/><circle cx="12" cy="17" r="4" fill="@c"/>'),
    "species": ("physics", '<path d="M7 7l5 5 5-5M12 12v6" stroke="@d" stroke-width="2"/><circle cx="7" cy="7" r="3" fill="#1e88e5"/><circle cx="17" cy="7" r="3" fill="#e5383b"/><circle cx="12" cy="18" r="3.4" fill="@c"/>'),
    "ramp": ("physics", '<path d="M3 3v18h18" fill="none" stroke="@d" stroke-width="2" stroke-linecap="round"/><path d="M5 18C10 18 11 6 20 6" fill="none" stroke="@c" stroke-width="3" stroke-linecap="round"/><circle cx="20" cy="6" r="1.8" fill="#e5383b"/>'),
    "control": ("physics", '<rect x="2.5" y="8" width="19" height="8" rx="4" fill="@l"/><circle cx="16.5" cy="12" r="3.6" fill="@c"/><path d="M6 12h4" stroke="@d" stroke-width="2" stroke-linecap="round"/>'),
    "prop": ("physics", '<rect x="3" y="3" width="18" height="18" rx="2.5" fill="@l"/><path d="M6.5 8.5h5M14 8.5h3.5M6.5 15.5h2.5M12 15.5h5.5" stroke="@d" stroke-width="2" stroke-linecap="round"/><circle cx="12.5" cy="8.5" r="1.7" fill="@c"/><circle cx="10.5" cy="15.5" r="1.7" fill="@c"/>'),
    "particles": ("physics", '<circle cx="6" cy="7" r="2.6" fill="@c"/><circle cx="16" cy="5.5" r="2" fill="@d"/><circle cx="12" cy="12" r="3" fill="#1e88e5"/><circle cx="19" cy="14" r="2.6" fill="@c"/><circle cx="6.5" cy="17.5" r="2.2" fill="@d"/><circle cx="14" cy="19" r="1.8" fill="@l"/>'),
    # -- fire --------------------------------------------------------------------------------------
    "flame": ("fire", '<path d="M12 2c1 4.2 6.5 6.2 6.5 12.2a6.5 6.5 0 0 1-13 0C5.5 11 7.5 9.5 8.5 6.8c1.2 1 2 2.2 2.2 3.8C12 8.5 12.4 5.5 12 2z" fill="@c"/><path d="M12 21.5a3.8 3.8 0 0 1-3.8-3.8c0-2.6 2.6-3.5 3.8-6 1.2 2.5 3.8 3.4 3.8 6a3.8 3.8 0 0 1-3.8 3.8z" fill="#ffca28"/>'),
    "burner": ("fire", '<rect x="3" y="18" width="18" height="3.5" rx="1" fill="#555"/><path d="M12 3c.8 3.2 5 4.8 5 9.3a5 5 0 0 1-10 0C7 9.8 8.6 8.6 9.4 6.5c.9.8 1.6 1.6 1.7 2.9C12 7.5 12.3 5.4 12 3z" fill="@c"/><path d="M12 17.5a2.8 2.8 0 0 1-2.8-2.8c0-1.9 1.9-2.6 2.8-4.4.9 1.8 2.8 2.5 2.8 4.4a2.8 2.8 0 0 1-2.8 2.8z" fill="#ffca28"/>'),
    "heat": ("fire", '<path d="M5 17c-1.5-2 1.5-3.5 0-6M12 17c-1.5-2 1.5-3.5 0-6M19 17c-1.5-2 1.5-3.5 0-6" fill="none" stroke="@c" stroke-width="2.4" stroke-linecap="round"/><path d="M3 21h18" stroke="@d" stroke-width="2.4" stroke-linecap="round"/>'),
    "thermometer": ("fire", '<rect x="9.5" y="2.5" width="5" height="13.5" rx="2.5" fill="#cfd8dc"/><circle cx="12" cy="17.8" r="4.3" fill="#e5383b"/><rect x="11" y="7" width="2" height="11" fill="#e5383b"/><path d="M16.5 5h3M16.5 8h2M16.5 11h3" stroke="#78909c" stroke-width="1.4" stroke-linecap="round"/>'),
    "smoke": ("fire", '<path d="M7 19a4.5 4.5 0 0 1-.5-9 5.5 5.5 0 0 1 10.6-1A4.8 4.8 0 0 1 17 19z" fill="#90a4ae"/><path d="M7.5 19a4 4 0 0 1-.4-7 5 5 0 0 1 4.9-3.6A5.5 5.5 0 0 0 9 14c0 1.7.6 3.2 1.7 5z" fill="#b0bec5"/>'),
    # -- devices -----------------------------------------------------------------------------------
    "device": ("device", '<circle cx="12" cy="12" r="9.5" fill="@l"/><circle cx="12" cy="12" r="5.8" fill="@c"/><circle cx="12" cy="12" r="2.4" fill="#fff"/>'),
    "heatdet": ("device", '<ellipse cx="12" cy="18" rx="9.5" ry="3.6" fill="@d"/><path d="M5 18a7 7 0 0 1 14 0z" fill="@c"/><path d="M7 7.5a7 6 0 0 1 10 0M9.2 10a4 3.4 0 0 1 5.6 0" fill="none" stroke="#e5383b" stroke-width="2" stroke-linecap="round"/>'),
    "smokedet": ("device", '<ellipse cx="12" cy="18" rx="9.5" ry="3.6" fill="@d"/><path d="M5 18a7 7 0 0 1 14 0z" fill="@c"/><path d="M8 11c-1.5-1.5 1.5-2.8 0-4.5M13 11c-1.5-1.5 1.5-2.8 0-4.5M17.5 11c-1.2-1.4 1.2-2.4 0-4" fill="none" stroke="#90a4ae" stroke-width="2" stroke-linecap="round"/>'),
    "beamdet": ("device", '<rect x="2" y="8" width="5" height="8" rx="1.2" fill="@d"/><rect x="17" y="8" width="5" height="8" rx="1.2" fill="@c"/><path d="M7.5 12h9" stroke="#e5383b" stroke-width="2" stroke-dasharray="2.5 1.8" stroke-linecap="round"/>'),
    "gas": ("device", '<circle cx="12" cy="12" r="9.5" fill="@l"/><path d="M6.5 14.5c1.5-3 3-3 4.5 0s3 3 4.5 0" fill="none" stroke="@c" stroke-width="2.4" stroke-linecap="round"/><path d="M6.5 10c1.5-3 3-3 4.5 0s3 3 4.5 0" fill="none" stroke="@d" stroke-width="2.4" stroke-linecap="round"/>'),
    "anemometer": ("device", '<path d="M3 9h10a3 3 0 1 0-3-3M3 14h14a3 3 0 1 1-3 3M3 19h6" fill="none" stroke="@c" stroke-width="2.4" stroke-linecap="round"/>'),
    "gauge": ("device", '<circle cx="12" cy="12" r="9.5" fill="@l"/><path d="M5.2 15a7 7 0 1 1 13.6 0" fill="none" stroke="@c" stroke-width="2"/><path d="M12 13 16.5 7.5" stroke="#e5383b" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="13" r="1.8" fill="@d"/>'),
    "nozzle": ("device", '<path d="M12 2.5c3.5 4.5 5.5 7.5 5.5 10.2a5.5 5.5 0 0 1-11 0C6.5 10 8.5 7 12 2.5z" fill="#29b6f6"/><path d="M9.5 13a2.5 2.5 0 0 0 2 2.8" fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/><path d="M12 18.5v3M8 20l1 1.5M16 20l-1 1.5" stroke="@c" stroke-width="1.8" stroke-linecap="round"/>'),
    "heatflux": ("device", '<circle cx="12" cy="12" r="4.5" fill="#ffb300"/><g stroke="#ef8a00" stroke-width="2.2" stroke-linecap="round"><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/></g>'),
    "sensorline": ("device", '<path d="M3 20h18" stroke="@d" stroke-width="2"/><path d="M12 20V6" stroke="@c" stroke-width="2.2"/><circle cx="12" cy="6" r="3" fill="#e5383b"/><circle cx="12" cy="11" r="1.8" fill="@c"/><circle cx="12" cy="15.5" r="1.8" fill="@c"/>'),
    # -- output --------------------------------------------------------------------------------------
    "slice": ("output", '<path d="M3 17 8 5.5h13L16 17z" fill="@c"/><path d="M6.5 13.5 9.5 7h9.2l-3 6.5z" fill="@l"/><path d="M8 15.2l2.4-5.3h5.2" fill="none" stroke="#f2a900" stroke-width="2"/><path d="M3 20.5h13" stroke="@d" stroke-width="2"/>'),
    "boundary": ("output", '<path d="M12 2.5 21 7l-9 4.5L3 7z" fill="@l"/><path d="M3 7l9 4.5v10L3 17z" fill="@d"/><path d="M21 7l-9 4.5v10l9-4.5z" fill="#ef8a00"/>'),
    "iso": ("output", '<path d="M12 2.5c5.5 0 9.5 4 9.5 8.5 0 3.5-3 5.5-3 8.5s-3.5 2-6 2-6.5-2.5-6.5-7S4 2.5 12 2.5z" fill="@c"/><ellipse cx="9.5" cy="8.5" rx="3.2" ry="2.2" fill="#fff" opacity=".5"/>'),
    "plot3d": ("output", '<path d="M12 2.5 21 7v10l-9 4.5L3 17V7z" fill="@l"/><path d="M3 7l9 4.5L21 7M12 11.5v10M7.5 4.8l9 4.5M7.5 9.5l9 4.5M16.5 4.8 7.5 9.3" fill="none" stroke="@c" stroke-width="1.5"/><path d="M12 2.5 21 7v10l-9 4.5L3 17V7z" fill="none" stroke="@d" stroke-width="1.8" stroke-linejoin="round"/>'),
    "profile": ("output", '<path d="M5 3v18M5 21h16" fill="none" stroke="@d" stroke-width="2" stroke-linecap="round"/><path d="M6.5 20C16 17 8 12.5 14 9.5s4-5 5-6.5" fill="none" stroke="@c" stroke-width="2.8" stroke-linecap="round"/>'),
    "vectors": ("output", '<g stroke="@c" stroke-width="2.2" stroke-linecap="round"><path d="M4 8h7M4 16h7M13 12h7"/></g><path d="M13 8l-3.5-2.4v4.8zM13 16l-3.5-2.4v4.8zM22 12l-3.5-2.4v4.8z" fill="@d"/>'),
    "colorbar": ("output", '<rect x="8" y="2.5" width="8" height="19" rx="2" fill="#e5383b"/><path d="M8 7v-2.5A2 2 0 0 1 10 2.5h4A2 2 0 0 1 16 4.5V7z" fill="#e5383b"/><rect x="8" y="7" width="8" height="3.6" fill="#ffb300"/><rect x="8" y="10.6" width="8" height="3.6" fill="#8bc34a"/><rect x="8" y="14.2" width="8" height="3.6" fill="#29b6f6"/><path d="M8 17.8v1.7a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-1.7z" fill="#5e35b1"/>'),
    "rendering": ("output", '<path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z" fill="@c"/><path d="M19 3l.9 2.1L22 6l-2.1.9L19 9l-.9-2.1L16 6l2.1-.9z" fill="#ffca28"/>'),
    # -- hvac ------------------------------------------------------------------------------------------
    "duct": ("hvac", '<rect x="2" y="7.5" width="20" height="9" rx="1.5" fill="@c"/><rect x="2" y="9.5" width="20" height="1.8" fill="@l"/><rect x="7.5" y="5.5" width="2.2" height="13" rx=".6" fill="@d"/><rect x="14.3" y="5.5" width="2.2" height="13" rx=".6" fill="@d"/>'),
    "fan": ("hvac", '<g fill="@c"><path d="M12 12C11 6 13 2.5 17 3.5c1.5 3.5-.5 7.5-5 8.5z"/><path d="M12 12C18 11 21.5 13 20.5 17c-3.5 1.5-7.500-.5-8.500-5z"/><path d="M12 12C13 18 11 21.500 7 20.500c-1.500-3.500.500-7.500 5-8.500z"/><path d="M12 12C6 13 2.500 11 3.500 7c3.500-1.500 7.500.500 8.500 5z"/></g><circle cx="12" cy="12" r="2.4" fill="@d"/>'),
    "node": ("hvac", '<circle cx="12" cy="12" r="9.5" fill="@l"/><circle cx="12" cy="12" r="5.5" fill="@c"/><path d="M12 2.5V6.5M12 17.5v4M2.5 12h4M17.5 12h4" stroke="@d" stroke-width="2"/>'),
    "damper": ("hvac", '<rect x="3" y="3" width="18" height="18" rx="2" fill="@l" stroke="@c" stroke-width="2"/><path d="M6 7.5 18 10M6 12 18 14.5M6 16.5l12 2.5" stroke="@d" stroke-width="2.2" stroke-linecap="round"/>'),
    "hvacfilter": ("hvac", '<path d="M3 4h18l-6.5 8.5V20l-5-2.5v-5z" fill="@c"/><path d="M5.5 5.8h13" stroke="@l" stroke-width="1.6"/>'),
    "aircoil": ("hvac", '<path d="M3 12h2.5l2-6 3 12 3-12 3 12 2-6H21" fill="none" stroke="@c" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 20.5h18" stroke="#29b6f6" stroke-width="2.2" stroke-linecap="round"/>'),
    "leak": ("hvac", '<path d="M3 8h10l3 3-3 3H3z" fill="@c"/><path d="M17 17.5c1.2 1.8 2 3 2 4.200a2 2 0 0 1-4 0c0-1.200.8-2.400 2-4.200z" fill="#29b6f6"/><path d="M18 5l3 3-3 3" fill="none" stroke="@d" stroke-width="2" stroke-linecap="round"/>'),
    # -- run / check -------------------------------------------------------------------------------------
    "run": ("run", '<circle cx="12" cy="12" r="10" fill="@c"/><path d="M9.5 6.5 18 12l-8.5 5.5z" fill="#fff"/>'),
    "play": ("run", '<path d="M6 3.5 20.5 12 6 20.5z" fill="@c"/>'),
    "pause": ("run", '<rect x="5.5" y="3.5" width="4.5" height="17" rx="1.2" fill="@c"/><rect x="14" y="3.5" width="4.5" height="17" rx="1.2" fill="@c"/>'),
    "stop": ("run", '<rect x="4.5" y="4.5" width="15" height="15" rx="2.5" fill="#e5383b"/>'),
    "stepback": ("run", '<rect x="4" y="4.5" width="3" height="15" rx="1" fill="@d"/><path d="M20 4.5v15L8.500 12z" fill="@c"/>'),
    "stepfwd": ("run", '<rect x="17" y="4.5" width="3" height="15" rx="1" fill="@d"/><path d="M4 4.5v15L15.500 12z" fill="@c"/>'),
    "tostart": ("run", '<rect x="3.5" y="4.5" width="3" height="15" rx="1" fill="@d"/><path d="M20.500 4.5v15L8.500 12z" fill="@c"/>'),
    "toend": ("run", '<rect x="17.500" y="4.5" width="3" height="15" rx="1" fill="@d"/><path d="M3.500 4.5v15L15.500 12z" fill="@c"/>'),
    "validate": ("run", '<path d="M12 2.5 20.500 5.500v6c0 5.200-3.500 8.800-8.500 10.500C7 20.300 3.500 16.700 3.500 11.500v-6z" fill="@c"/><path d="M8 12l3 3 5-6" fill="none" stroke="#fff" stroke-width="2.600" stroke-linecap="round" stroke-linejoin="round"/>'),
    "autofix": ("run", '<path d="M4 20 14 10" stroke="@d" stroke-width="3.200" stroke-linecap="round"/><path d="M15.500 2.500l1.300 3.200 3.200 1.300-3.200 1.300-1.300 3.200-1.300-3.200L11 7l3.200-1.300z" fill="#ffca28"/><circle cx="6" cy="6" r="1.500" fill="@c"/><circle cx="19" cy="17.500" r="1.500" fill="@c"/>'),
    "repair": ("run", '<path d="M14.500 3.500a5 5 0 0 0-4.500 6.800L3 17.300 6.700 21l7-7a5 5 0 0 0 6.800-4.500l-3.200 3.200-3.100-.8-.8-3.100z" fill="@c"/><circle cx="6.200" cy="17.800" r="1.100" fill="#fff"/>'),
    "simparams": ("run", '<path d="M4 7h16M4 12h16M4 17h16" stroke="@d" stroke-width="2.200" stroke-linecap="round"/><circle cx="8" cy="7" r="2.800" fill="@c"/><circle cx="15" cy="12" r="2.800" fill="#f2a900"/><circle cx="10" cy="17" r="2.800" fill="@c"/>'),
    # -- results --------------------------------------------------------------------------------------------
    "results": ("result", '<rect x="3" y="12" width="4.500" height="9" rx="1" fill="@d"/><rect x="9.800" y="7" width="4.500" height="14" rx="1" fill="@c"/><rect x="16.500" y="3" width="4.500" height="18" rx="1" fill="#f2a900"/>'),
    "viewer3d": ("result", '<path d="M12 2.500 21 7v10l-9 4.500L3 17V7z" fill="@c"/><path d="M12 2.500 21 7l-9 4.500L3 7z" fill="@l"/><circle cx="16.500" cy="16.500" r="5" fill="#fff"/><circle cx="16.500" cy="16.500" r="2.600" fill="#f2a900"/>'),
    "monitor": ("result", '<rect x="2.500" y="3.500" width="19" height="13" rx="2" fill="@d"/><rect x="4.500" y="5.500" width="15" height="9" fill="#fff"/><path d="M5.500 12.500l3-3 3 2 3-4 2.500 3" fill="none" stroke="#e5383b" stroke-width="1.800" stroke-linejoin="round"/><path d="M8 20.500h8M12 16.500v4" stroke="@d" stroke-width="2.200"/>'),
    "movie": ("result", '<rect x="2.500" y="5" width="19" height="14" rx="2" fill="@c"/><path d="M6 5v14M18 5v14" stroke="@d" stroke-width="3.400"/><g fill="#fff"><rect x="3.600" y="7" width="1.600" height="1.600"/><rect x="3.600" y="11.200" width="1.600" height="1.600"/><rect x="3.600" y="15.400" width="1.600" height="1.600"/><rect x="18.800" y="7" width="1.600" height="1.600"/><rect x="18.800" y="11.200" width="1.600" height="1.600"/><rect x="18.800" y="15.400" width="1.600" height="1.600"/></g><path d="M10.500 9v6l4.500-3z" fill="#fff"/>'),
    "movie360": ("result", '<circle cx="12" cy="12" r="9.500" fill="@c"/><ellipse cx="12" cy="12" rx="4" ry="9.500" fill="none" stroke="@l" stroke-width="1.600"/><path d="M2.500 12h19" stroke="@l" stroke-width="1.600"/><path d="M10 9v6l5-3z" fill="#fff"/>'),
    "csv": ("result", '<path d="M5 2h10l5 5v15H5z" fill="@l"/><path d="M15 2v5h5z" fill="@d"/><path d="M8 11.500h9M8 15h9M8 18.500h9M12.500 10v10" stroke="@c" stroke-width="1.500"/>'),
    "chart": ("result", '<path d="M3 3v18h18" fill="none" stroke="@d" stroke-width="2" stroke-linecap="round"/><path d="M5.500 16 10 11l3.500 3L20 6" fill="none" stroke="@c" stroke-width="2.800" stroke-linecap="round" stroke-linejoin="round"/><circle cx="10" cy="11" r="1.600" fill="#f2a900"/><circle cx="13.500" cy="14" r="1.600" fill="#f2a900"/>'),
    "image": ("result", '<rect x="2.500" y="4" width="19" height="16" rx="2" fill="@l"/><circle cx="8" cy="9.500" r="2.200" fill="#ffca28"/><path d="M2.500 17.500 9 12l4 3.500 3.500-3L21.500 17v1.500a1.500 1.500 0 0 1-1.500 1.500H4a1.500 1.500 0 0 1-1.500-1.500z" fill="@c"/>'),
    "report": ("result", '<path d="M5 2h10l5 5v15H5z" fill="#fff" stroke="@c" stroke-width="2" stroke-linejoin="round"/><path d="M15 2v5h5" fill="@l"/><path d="M8.500 11h7M8.500 14.500h7M8.500 18h4" stroke="@d" stroke-width="1.800" stroke-linecap="round"/>'),
    "errors": ("result", '<path d="M12 3 22 20.500H2z" fill="#f2a900"/><path d="M12 9.500v5.500" stroke="#fff" stroke-width="2.400" stroke-linecap="round"/><circle cx="12" cy="17.800" r="1.400" fill="#fff"/>'),
    # -- library ---------------------------------------------------------------------------------------------
    "library": ("library", '<rect x="3" y="4" width="4.500" height="17" rx="1" fill="@c"/><rect x="9" y="3" width="4.500" height="18" rx="1" fill="#1e88e5"/><rect x="14.500" y="6" width="4.500" height="15" rx="1" fill="#ef8a00" transform="rotate(-8 16.500 21)"/>'),
    "database": ("library", '<ellipse cx="12" cy="6" rx="8" ry="3" fill="@l"/><path d="M4 6v6c0 1.700 3.600 3 8 3s8-1.300 8-3V6" fill="@c"/><path d="M4 12v6c0 1.700 3.600 3 8 3s8-1.300 8-3v-6" fill="@d"/>'),
    "assistant": ("library", '<path d="M12 2l2.600 7.400L22 12l-7.400 2.600L12 22l-2.600-7.400L2 12l7.400-2.600z" fill="#7e57c2"/><path d="M19 2.500l.8 2.200 2.200.8-2.200.8-.8 2.200-.8-2.200-2.200-.8 2.200-.8z" fill="#ffca28"/>'),
    # -- annotation / time / info -----------------------------------------------------------------------------
    "dimension": ("annotate", '<path d="M3 6v12M21 6v12" stroke="@d" stroke-width="2.200" stroke-linecap="round"/><path d="M5 12h14" stroke="@c" stroke-width="2.200"/><path d="M5 12l3.500-2.800v5.600zM19 12l-3.500-2.800v5.600z" fill="@c"/>'),
    "label": ("annotate", '<path d="M3 4h9.500l8.500 8.500-8.500 8.500L3 12.500z" fill="@c"/><circle cx="7.500" cy="8.500" r="1.800" fill="#fff"/>'),
    "tour": ("annotate", '<path d="M5 20c0-6 7-4 7-9S6 7 8 4" fill="none" stroke="@c" stroke-width="2.400" stroke-dasharray="3 2.400" stroke-linecap="round"/><circle cx="5" cy="20" r="2.400" fill="@d"/><path d="M18 3l3.500 3-3.500 3z" fill="#e5383b"/><path d="M18 3v8" stroke="@d" stroke-width="2"/>'),
    "keyframe": ("annotate", '<path d="M12 2.500 21.500 12 12 21.500 2.500 12z" fill="@c"/><path d="M12 6.500 17.500 12 12 17.500 6.500 12z" fill="#fff"/>'),
    "viewsaved": ("annotate", '<rect x="2.500" y="5" width="19" height="14" rx="2" fill="@l" stroke="@c" stroke-width="2"/><circle cx="12" cy="12" r="3.600" fill="@c"/><circle cx="12" cy="12" r="1.500" fill="#fff"/>'),
    "time": ("time", '<circle cx="12" cy="12" r="9.500" fill="@c"/><circle cx="12" cy="12" r="7.200" fill="#fff"/><path d="M12 7v5.500l3.500 2" fill="none" stroke="@d" stroke-width="2.200" stroke-linecap="round"/>'),
    "help": ("info", '<circle cx="12" cy="12" r="10" fill="@c"/><path d="M8.800 9.500a3.300 3.300 0 1 1 5 2.800c-1.200.8-1.800 1.300-1.800 2.500" fill="none" stroke="#fff" stroke-width="2.400" stroke-linecap="round"/><circle cx="12" cy="18" r="1.500" fill="#fff"/>'),
    "about": ("info", '<circle cx="12" cy="12" r="10" fill="@c"/><circle cx="12" cy="7.200" r="1.600" fill="#fff"/><path d="M12 11v7" stroke="#fff" stroke-width="2.600" stroke-linecap="round"/>'),
    "update": ("info", '<path d="M7 19a4.500 4.500 0 0 1-.5-9 5.500 5.500 0 0 1 10.600-1A4.800 4.800 0 0 1 17 19z" fill="@l"/><path d="M12 17v-6M9 13.500l3-3 3 3" fill="none" stroke="@c" stroke-width="2.400" stroke-linecap="round" stroke-linejoin="round"/>'),
    "shortcuts": ("info", '<rect x="2.500" y="6" width="19" height="12" rx="2.500" fill="@c"/><path d="M6 10h2M10 10h2M14 10h2M18 10h.5M7 14h10" stroke="#fff" stroke-width="1.800" stroke-linecap="round"/>'),
    "fdsfile": ("file", '<path d="M5 2h10l5 5v15H5z" fill="@l"/><path d="M15 2v5h5z" fill="@d"/><path d="M12.500 11.500c.5 2 3 3 3 5.700a3 3 0 0 1-6 0c0-1.600 1-2.200 1.600-3.500.5.500.9 1 1 1.800.5-1 .5-2.500.4-4z" fill="#e5383b"/>'),
    "cpu": ("run", '<rect x="6" y="6" width="12" height="12" rx="2" fill="@c"/><rect x="9" y="9" width="6" height="6" rx="1" fill="@l"/><path d="M9 2.500v3.500M15 2.500v3.500M9 18v3.500M15 18v3.500M2.500 9H6M2.500 15H6M18 9h3.500M18 15h3.500" stroke="@d" stroke-width="1.800" stroke-linecap="round"/>'),
    "calc": ("annotate", '<rect x="4" y="2.500" width="16" height="19" rx="2.500" fill="@c"/><rect x="6.500" y="5" width="11" height="4.500" rx="1" fill="#fff"/><g fill="@l"><rect x="6.500" y="12" width="3" height="3" rx=".6"/><rect x="10.500" y="12" width="3" height="3" rx=".6"/><rect x="14.500" y="12" width="3" height="3" rx=".6"/><rect x="6.500" y="16.500" width="3" height="3" rx=".6"/><rect x="10.500" y="16.500" width="3" height="3" rx=".6"/></g><rect x="14.500" y="16.500" width="3" height="3" rx=".6" fill="#f2a900"/>'),
    "console": ("annotate", '<rect x="2.500" y="4" width="19" height="16" rx="2.500" fill="#263238"/><path d="M6.500 9.500 10 12.500l-3.500 3" fill="none" stroke="#7bd88f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M12 16h5" stroke="@l" stroke-width="2" stroke-linecap="round"/>'),
    "plugin": ("annotate", '<path d="M9 2.500v4M15 2.500v4" stroke="@d" stroke-width="2.600" stroke-linecap="round"/><path d="M5.500 6.500h13v5a6.500 6.500 0 0 1-13 0z" fill="@c"/><path d="M12 18v3.500" stroke="@d" stroke-width="2.600" stroke-linecap="round"/>'),
    "warning": ("warn", '<path d="M12 3 22 20.5H2z" fill="@c"/><path d="M12 9.5v5.5" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="17.8" r="1.4" fill="#fff"/>'),
    "dot": ("info", '<circle cx="12" cy="12" r="5" fill="@c"/>'),
    # -- application icons -----------------------------------------------------------------------------------------
    "app_pyfds": ("fire", '<rect x="1.500" y="1.500" width="21" height="21" rx="5" fill="#263238"/><path d="M12 3.500c1 4 6 5.800 6 11.200a6 6 0 0 1-12 0C6 11.700 8 10.300 9 7.800c1 .9 1.800 2 2 3.500C12.200 9.200 12.500 6.200 12 3.500z" fill="#e5383b"/><path d="M12 20.500a3.500 3.500 0 0 1-3.500-3.500c0-2.400 2.400-3.200 3.500-5.500 1.100 2.300 3.500 3.100 3.500 5.500a3.500 3.500 0 0 1-3.500 3.500z" fill="#ffca28"/>'),
    "app_results": ("result", '<rect x="1.500" y="1.500" width="21" height="21" rx="5" fill="#263238"/><path d="M12 4.500 19.500 8.500v7L12 19.500 4.500 15.500v-7z" fill="#0097a7"/><path d="M12 4.500l7.500 4L12 12.500 4.500 8.500z" fill="#4dd0e1"/><path d="M4.500 8.500l7.500 4v7l-7.500-4z" fill="#00676f"/><circle cx="17" cy="17" r="4.200" fill="#263238"/><path d="M13 17h8" stroke="#ffca28" stroke-width="1.800" stroke-linecap="round"/><path d="M17 13v8" stroke="#e5383b" stroke-width="1.800" stroke-linecap="round"/>'),
}
