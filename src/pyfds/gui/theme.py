"""Light and dark themes (UI-09): a Fusion palette, remembered between sessions."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

THEMES = ("light", "dark")


def palette(name: str) -> QPalette:
    if name not in THEMES:
        raise ValueError(f"unknown theme {name!r}; choose from {', '.join(THEMES)}")
    p = QPalette()
    if name == "light":
        return p
    window, base, text, mid, highlight = "#2b2b2b", "#1e1e1e", "#e6e6e6", "#3c3c3c", "#2f6fb5"
    for role, color in ((QPalette.Window, window), (QPalette.WindowText, text), (QPalette.Base, base),
                        (QPalette.AlternateBase, window), (QPalette.ToolTipBase, window), (QPalette.ToolTipText, text),
                        (QPalette.Text, text), (QPalette.Button, mid), (QPalette.ButtonText, text),
                        (QPalette.BrightText, "#ff5555"), (QPalette.Link, "#6aa9ff"), (QPalette.Highlight, highlight),
                        (QPalette.HighlightedText, "#ffffff"), (QPalette.PlaceholderText, "#8a8a8a")):
        p.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#7a7a7a"))
    return p


def saved_theme() -> str:
    value = QSettings("PyFDS", "PyFDS").value("theme", "light")
    return value if value in THEMES else "light"


def apply_theme(name: str, app: Optional[QApplication] = None, remember: bool = True) -> str:
    """Apply a theme to the whole application and (by default) remember the choice."""
    app = app or QApplication.instance()
    pal = palette(name)
    if app is not None:
        app.setStyle("Fusion")
        app.setPalette(pal)
    if remember:
        QSettings("PyFDS", "PyFDS").setValue("theme", name)
    return name
