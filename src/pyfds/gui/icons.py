"""Task-based, multi-coloured icons for both applications (the model editor and the Results viewer).

Nothing is loaded from disk: every icon is a small SVG (``icon_glyphs``) rendered at several sizes, so it stays sharp on
high-DPI screens and the colours are one table (``TASK_COLORS``). The colour tells the task:

    blue    geometry and drawing        orange   physics (surfaces, materials, reactions)
    red     fire and heat               green    devices and sensors; run and check
    purple  output (slices, isosurfaces) teal     HVAC            cyan   results and plots
    slate   edit and transform          indigo   camera and display   pink  dimensions, labels, tours

Public API
    icon(key, task=None, gray=False, badge=None)  a QIcon for a glyph key ("mesh"; "mesh+add" adds a corner badge: add,
                                            import, export, library, open; "undo@view" recolours it to another task)
    icon_for_text(text, menu="")            the icon for a menu / toolbar entry, chosen from its wording
    icon_for_entity(attr, entity=None)      the Project Explorer row of a model object
    icon_for_node(kind, label)              the Navigation View row of a results node
    install_icons(window)                   icons on every menu action and toolbar of a main window, and the window icon
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QMenu, QToolBar, QWidget

from .icon_commands import COMMAND_GLYPHS, OPTION_MENUS
from .icon_glyphs import GLYPHS, TASK_COLORS

SIZES = (16, 20, 24, 32, 48)
_cache: Dict[Tuple[str, str, bool, str], QIcon] = {}

# corner badges: a disc in the lower right with the verb, so "Import Materials" shows a material that comes in and
# "Add Mesh" a mesh with a plus, instead of every Import / Add entry of a menu showing the same picture
_BADGES = {
    "add": ("#2e9e2e", '<path d="M18 14.6v6.8M14.6 18h6.8" stroke="#fff" stroke-width="2" stroke-linecap="round"/>'),
    "import": ("#3f6fb5", '<path d="M18 14.3v6.2M15.3 17.9 18 20.6l2.7-2.7" fill="none" stroke="#fff" stroke-width="1.8" '
                          'stroke-linecap="round" stroke-linejoin="round"/>'),
    "export": ("#3f6fb5", '<path d="M18 21.7v-6.2M15.3 18.1 18 15.4l2.7 2.7" fill="none" stroke="#fff" stroke-width="1.8" '
                          'stroke-linecap="round" stroke-linejoin="round"/>'),
    "library": ("#8d6e63", '<path d="M15.2 15v6M18 15v6" stroke="#fff" stroke-width="1.7"/>'
                           '<path d="M20 15.2l1.6 5.6" stroke="#ffca28" stroke-width="1.7"/>'),
    "open": ("#00897b", '<path d="M14.6 18h6.8M16.3 16.3 14.6 18l1.7 1.7M19.7 16.3l1.7 1.7-1.7 1.7" fill="none" stroke="#fff" '
                        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'),
}


def _shade(color: str, factor: int) -> str:
    return QColor(color).darker(factor).name() if factor > 100 else QColor(color).lighter(-factor).name()


def _svg(key: str, task: Optional[str], badge: str = "") -> str:
    own_task, body = GLYPHS[key]
    c = TASK_COLORS[task or own_task]
    body = body.replace("@c", c).replace("@d", _shade(c, 140)).replace("@l", _shade(c, -170))
    if badge:
        fill, mark = _BADGES[badge]
        body = (f'<g transform="scale(.84)">{body}</g>'
                f'<circle cx="18" cy="18" r="5.6" fill="{fill}" stroke="#fff" stroke-width="1.2"/>{mark}')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


def _render(svg: str, size: int, gray: bool) -> QPixmap:
    ratio = 2                                                     # drawn at twice the size so it stays crisp on scaled screens
    img = QImage(size * ratio, size * ratio, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
    painter.end()
    if gray:
        img = img.convertToFormat(QImage.Format_ARGB32)
        for y in range(img.height()):
            for x in range(img.width()):
                p = QColor.fromRgba(img.pixel(x, y))
                g = int(0.3 * p.red() + 0.59 * p.green() + 0.11 * p.blue())
                img.setPixelColor(x, y, QColor(g, g, g, int(p.alpha() * 0.6)))
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(key: str, task: Optional[str] = None, gray: bool = False, badge: Optional[str] = None) -> QIcon:
    """The icon for glyph *key* (unknown keys give the plain dot). *task* recolours it to another task's colour;
    *gray* is the muted version used for disabled model objects; *badge* (or ``key+badge``) adds a corner badge."""
    if "@" in key:                                          # "undo@view": the glyph in another task's colour
        key, task = key.split("@", 1)
    if "+" in key:
        key, badge = key.split("+", 1)
    if key not in GLYPHS:
        key = "dot"
    badge = badge if badge in _BADGES else ""
    ck = (key, task or "", gray, badge)
    if ck not in _cache:
        svg = _svg(key, task, badge)
        out = QIcon()
        for s in SIZES:
            out.addPixmap(_render(svg, s, gray))
        _cache[ck] = out
    return _cache[ck]


def svg_text(key: str, task: Optional[str] = None, badge: str = "") -> str:
    """The SVG source of a glyph (used by the tests and by anyone who wants to export the picture)."""
    return _svg(key, task, badge)


# -- menu and toolbar wording -> glyph ---------------------------------------------------------------------------------
# first match wins; the text is lower case, without "&" and the trailing "..."
TEXT_RULES = [
    (r"reset to viewpoint", "resetview"), (r"^intersection", "intersection"), (r"time history", "chart"), (r"timelines", "time"),
    (r"show dimensions", "dimension"), (r"show labels", "label"), (r"viewpoint", "viewsaved"), (r"reset window layout", "resetview"),
    (r"set 3d window size", "fullscreen"), (r"skybox", "image"), (r"draw ramp", "viewside"), (r"draw stair", "floors"), (r"draw roof", "room"),
    (r"draw (door|window)", "door"), (r"^pause", "pause"), (r"^resume", "play"), (r"guide|manual|tutorial", "help"), (r"smokeview", "viewer3d"),
    (r"voxel|convert to blocks", "voxel"), (r"isometric", "viewcube"), (r"warning", "warning"), (r"isosurface|isof", "iso"), (r"draw vent", "vent"), (r"draw hole", "hole"), (r"draw floor|draw ceiling", "floors"), (r"open mesh boundaries", "vent"), (r"\.(pyfds|fds|pyfdsv)$", "fdsfile"),
    (r"fuel", "flame"), (r"all \(folder\)", "folder"), (r"network editor", "duct"), (r"solver setup", "settings"), (r"diagnostics", "errors"),
    (r"auto-assign|assign selected", "floors"), (r"openmp|\bmpi\b|\bgpu\b", "cpu"), (r"archive results", "export"), (r"restore results", "import"),
    (r"validat", "validate"), (r"plugin", "plugin"), (r"calculator", "calc"), (r"fds preview", "report"), (r"script console", "console"),
    (r"project explorer|navigation view", "folder"), (r"layouts|workspace", "split"), (r"user manual", "help"), (r"^examples", "viewcube"),
    (r"navigation tool", "orbit"), (r"fds actual|fds requested|^ge1", "box"), (r"date/time", "time"),
    (r"fahrenheit|kelvin|^default \(|concentration|mass fraction|^ppm", "units"), (r"^none$", "cancel"), (r"motion blur", "rendering"),
    (r"cache results", "database"),
    (r"^new from template", "new"), (r"^new results", "new"), (r"^new view", "viewsaved"), (r"^new tour", "tour"), (r"^new\b", "new"),
    (r"open results \(\.smv\)|^load results", "load"), (r"open results|^open\b", "open"), (r"^recent", "recent"),
    (r"^save as", "saveas"), (r"save screenshot", "camera"), (r"save 360", "movie360"), (r"save movie|record movie", "movie"),
    (r"save bookmark|load bookmark", "bookmark"), (r"^save", "save"),
    (r"^print", "print"),
    (r"preferences|project settings|snap settings|^general|^rendering|^3d smoke$|^floors", "settings"),
    (r"import views|^import", "import"), (r"export animation", "movie"), (r"export", "export"),
    (r"^exit|^quit", "exit"), (r"^close", "close"),
    (r"^select$", "select"), (r"^measure", "measure"), (r"^paint", "paint"), (r"^iso$", "viewcube"), (r"^ortho$", "ortho"),
    (r"^focus|^3d only", "focus"), (r"^panels", "panels"), (r"^toolbar", "toolbars"),
    (r"^undo", "undo"), (r"^redo", "redo"), (r"^cut", "cut"), (r"^copy", "copy"), (r"^paste", "paste"),
    (r"delete|remove section", "delete"), (r"duplicate", "duplicate"), (r"edit properties|^properties", "properties"),
    (r"^find|^replace", "find"), (r"select all|clear selection", "selectall"), (r"^filter", "filter"),
    (r"ungroup", "ungroup"), (r"group", "group"),
    (r"^move", "move"), (r"^rotate", "rotate"), (r"^scale", "scale"), (r"^mirror", "mirror"), (r"^snap", "snap"),
    (r"reset view|default view|reset camera", "resetview"), (r"standard views", "viewcube"),
    (r"^wireframe", "wireframe"), (r"^shaded|^solid", "shaded"), (r"^realistic", "realistic"),
    (r"show/hide|^show |^hide ", "eye"), (r"^grid", "grid"), (r"^axes", "axes"),
    (r"section", "section"), (r"split|horizontal|vertical|four-way", "split"), (r"fullscreen", "fullscreen"),
    (r"^theme|^light$|^dark$", "theme"), (r"units|metric|imperial", "units"),
    (r"^top$", "viewtop"), (r"^bottom$", "viewtop"), (r"^front$|^back$", "viewfront"), (r"left side|right side|^side|^left$|^right$", "viewside"),
    (r"orthogonal|projection", "ortho"), (r"perspective", "perspective"),
    (r"^orbit", "orbit"), (r"^pan", "pan"), (r"^zoom", "zoom"), (r"^roam", "roam"),
    (r"draw room", "room"), (r"cancel draw|^cancel", "cancel"),
    (r"boolean", "union"), (r"^union", "union"), (r"^difference", "difference"),
    (r"cylinder", "cylinder"), (r"sphere", "sphere"), (r"\bcone\b", "cone"), (r"\bpipe\b", "pipe"), (r"beam detector", "beamdet"),
    (r"\bbeam\b|column|girder", "beam"), (r"\bwall\b", "wall"), (r"\bdoor\b|window", "door"),
    (r"^draw|stl|geometry \(", "box"),
    (r"simulation parameters", "simparams"), (r"auto-?fix", "autofix"), (r"geometry repair", "repair"),
    (r"library|import from library", "library"), (r"database", "database"),
    (r"\bmesh", "mesh"), (r"obstruction", "box"), (r"\bvent", "vent"), (r"\bhole", "hole"),
    (r"surface", "surface"), (r"material", "material"), (r"reaction", "reaction"), (r"\bzone", "zone"), (r"species", "species"),
    (r"ramp", "ramp"), (r"control", "control"), (r"\bprop\b|property", "prop"), (r"init", "init"), (r"particle", "particles"),
    (r"floor", "floors"), (r"scenario", "scenario"), (r"\bgeom", "geom"),
    (r"heat flux", "heatflux"), (r"smoke detector", "smokedet"), (r"gas", "gas"), (r"anemometer|velocity probe", "anemometer"),
    (r"pressure", "gauge"), (r"nozzle|sprinkler", "nozzle"), (r"thermocouple|temperature", "thermometer"),
    (r"heat detector|detector", "heatdet"), (r"device labels", "label"), (r"outline", "shaded_outline"), (r"profile|\bline\b", "sensorline"), (r"device|devc", "device"),
    (r"slice", "slice"), (r"boundary|bndf", "boundary"), (r"plot3d", "plot3d"),
    (r"frequency|timeline|time display|^time", "time"),
    (r"duct", "duct"), (r"\bfan", "fan"), (r"node", "node"), (r"damper", "damper"), (r"filter", "hvacfilter"),
    (r"leak", "leak"), (r"coil", "aircoil"), (r"hvac", "duct"),
    (r"^stop", "stop"), (r"monitor", "monitor"), (r"^run|simulat", "run"),
    (r"view results|results viewer|smokeview|^viewer", "viewer3d"), (r"report", "report"),
    (r"time history|plot", "chart"), (r"csv", "csv"), (r"colorbar|colour|color", "colorbar"),
    (r"^dimension|add dimension", "dimension"), (r"label", "label"), (r"keyframe", "keyframe"), (r"tour", "tour"),
    (r"^refresh|follow", "refresh"), (r"unload", "unload"), (r"^load", "load"),
    (r"about", "about"), (r"check for updates|update", "update"), (r"shortcut|keyboard", "shortcuts"),
    (r"help|documentation|guide|tutorial", "help"), (r"assistant|agent|ai ", "assistant"),
    (r"^view|^camera", "viewcube"), (r"^results", "results"), (r"^edit", "properties"),
]
_COMPILED = [(re.compile(p), k) for p, k in TEXT_RULES]

# a menu's task colour, for entries no rule knows
MENU_TASKS = {"file": "file", "edit": "edit", "view": "view", "draw": "geometry", "model": "physics", "devices": "device", "output": "output",
              "hvac": "hvac", "run": "run", "results": "result", "tools": "annotate", "analysis": "result", "preferences": "file",
              "help": "info", "window": "view"}


def _clean(text: str) -> str:
    t = text.replace("&", "").strip().lower()
    return re.sub(r"(\.\.\.|…)$", "", t).strip()


def glyph_for_text(text: str) -> Optional[str]:
    """The glyph for a menu entry: its own entry in ``COMMAND_GLYPHS`` if it has one ("" = no icon), else the first
    wording rule that matches."""
    t = _clean(text)
    if t in COMMAND_GLYPHS:
        return COMMAND_GLYPHS[t]
    for rx, key in _COMPILED:
        if rx.search(t):
            return key
    return None


def icon_for_text(text: str, menu: str = "") -> QIcon:
    key = glyph_for_text(text)
    if key is None:
        return icon("dot", task=MENU_TASKS.get(_clean(menu), "file"))
    return icon(key) if key else QIcon()


# -- Project Explorer (the model editor's tree) ------------------------------------------------------------------------
ENTITY_GLYPHS = {
    "meshes": "mesh", "obstructions": "box", "vents": "vent", "holes": "hole", "surfaces": "surface", "devices": "device",
    "reactions": "reaction", "materials": "material", "ramps": "ramp", "inits": "init", "particles": "particles", "slices": "slice",
    "bndfs": "boundary", "isofs": "iso", "plot3ds": "plot3d", "profs": "profile", "hvac_nodes": "node", "hvac_ducts": "duct",
    "fans": "fan", "dampers": "damper", "hvac_filters": "hvacfilter", "hvac_leakages": "leak", "hvac_aircoils": "aircoil",
    "scenarios": "scenario", "floors": "floors", "groups": "folder", "geom": "geom",
}
_DEVICE_QUANTITIES = [("link temperature", "heatdet"), ("obscuration", "smokedet"), ("heat flux", "heatflux"), ("temperature", "thermometer"),
                      ("velocity", "anemometer"), ("pressure", "gauge"), ("volume fraction", "gas"), ("sprinkler", "nozzle"),
                      ("nozzle", "nozzle"), ("beam", "beamdet")]


def icon_for_entity(attr: str, entity=None, disabled: bool = False) -> QIcon:
    key = ENTITY_GLYPHS.get(attr, "dot")
    if attr == "devices" and entity is not None:
        q = str(getattr(entity, "quantity", "") or "").lower()
        key = next((g for word, g in _DEVICE_QUANTITIES if word in q), "device")
    return icon(key, gray=disabled)


# -- the Results viewer's Navigation View --------------------------------------------------------------------------------
NODE_KIND_GLYPHS = {
    "geometry": "box", "devices": "device", "view": "viewsaved", "smoke3d": "smoke", "slice2d": "slice", "slice3d": "slice", "slice_vectors": "vectors",
    "boundary": "boundary", "isosurface": "iso", "plot3d": "plot3d", "particles": "particles", "max_error": "errors",
    "data3d_iso": "iso", "data3d_slice": "slice", "data3d_point": "particles", "dimension": "dimension", "label": "label",
    "keyframe": "keyframe", "tour": "tour", "csv": "csv", "xy": "chart",
}
NODE_LABEL_RULES = [
    (r"scene geometry", "box"), (r"^views?$", "viewsaved"), (r"fds results", "results"), (r"3d smoke", "smoke"), (r"^plot3d$", "plot3d"),
    (r"2d slices|^slices$", "slice"), (r"maximum errors", "errors"), (r"^dimensions", "dimension"), (r"^labels", "label"),
    (r"xy plot", "chart"), (r"^points$", "particles"), (r"isosurfaces", "iso"), (r"particles", "particles"), (r"boundar", "boundary"),
    (r"vectors", "vectors"), (r"tours?$", "tour"), (r"temperature", "thermometer"), (r"soot|density|smoke", "smoke"),
    (r"hrr|heat release", "flame"), (r"velocity", "anemometer"), (r"pressure", "gauge"), (r"visibility", "eye"),
    (r"slice_|slice ", "slice"), (r"fed|species|fraction|co2|\bco\b", "gas"),
]
_NODE_COMPILED = [(re.compile(p), k) for p, k in NODE_LABEL_RULES]


def icon_for_node(kind: str, label: str = "") -> QIcon:
    if kind != "group":
        key = NODE_KIND_GLYPHS.get(kind)
        if key:
            return icon(key)
    t = label.strip().lower()
    for rx, key in _NODE_COMPILED:
        if rx.search(t):
            return icon(key)
    return icon("folder" if kind == "group" else "dot")


# -- installing on a window --------------------------------------------------------------------------------------------------
def _decorate_menu(menu: QMenu, top: str, seen: set) -> int:
    n = 0
    options = _clean(menu.title()) in OPTION_MENUS        # the choices of one setting: the check mark says it all
    for act in menu.actions():
        if act.isSeparator():
            continue
        if options and act.menu() is None:
            act.setIcon(QIcon())
            continue
        if act.icon().isNull():
            act.setIcon(icon_for_text(act.text(), top))
            n += 1
        sub = act.menu()
        if sub is not None and id(sub) not in seen:
            seen.add(id(sub))
            n += _decorate_menu(sub, top, seen)
    return n


def install_icons(window: QWidget, kind: str = "pyfds") -> int:
    """Give every menu entry and toolbar button of *window* its icon, set the toolbars to show icon and text, and set the window
    icon (*kind* ``"pyfds"`` or ``"results"``). Returns how many actions got an icon."""
    n = 0
    seen: set = set()
    mb = window.menuBar() if hasattr(window, "menuBar") else None
    if mb is not None:
        for act in mb.actions():
            menu = act.menu()
            if menu is not None:
                seen.add(id(menu))
                n += _decorate_menu(menu, _clean(act.text()), seen)
    for bar in window.findChildren(QToolBar):
        for act in bar.actions():
            if not act.isSeparator() and act.icon().isNull():
                act.setIcon(icon_for_text(act.text()))
                n += 1
        bar.setIconSize(QSize(20, 20))
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    window.setWindowIcon(icon("app_results" if kind == "results" else "app_pyfds"))
    return n
