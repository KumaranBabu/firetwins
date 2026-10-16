"""Tutorials (Help): the tutorial and manual documents shipped in ``docs/manuals_and_tutorials``, opened in the system's
viewer. The folder is found from the installation; if it is missing the dialog says where it looked."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

_SUFFIX = re.compile(r"\s*[_-]\s*Thunderhead Support\s*$", re.I)
_LEAD_YEAR = re.compile(r"^\d{4}\.\d+\s+")


def docs_root() -> Path:
    """``docs/manuals_and_tutorials`` next to the source tree (it is not part of an installed package)."""
    return Path(__file__).resolve().parents[3] / "docs" / "manuals_and_tutorials"


def find_tutorials(root: Optional[Path] = None) -> List[Dict[str, str]]:
    """``[{"title", "group", "path"}]`` for every PDF below *root*, grouped by sub-folder and sorted by title."""
    root = Path(root) if root is not None else docs_root()
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*.pdf")):
        title = _LEAD_YEAR.sub("", _SUFFIX.sub("", p.stem)).replace("_", " ").strip()
        group = p.parent.relative_to(root).as_posix() if p.parent != root else "General"
        out.append({"title": title, "group": group, "path": str(p)})
    return sorted(out, key=lambda d: (d["group"].lower(), d["title"].lower()))


class TutorialsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, root: Optional[Path] = None, opener=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tutorials")
        self.resize(620, 480)
        self.root = Path(root) if root is not None else docs_root()
        self._open = opener or (lambda path: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        self.items = find_tutorials(self.root)
        v = QVBoxLayout(self)
        self.note = QLabel("", self)
        self.note.setWordWrap(True)
        v.addWidget(self.note)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Filter by title or folder...")
        self.filter.textChanged.connect(lambda _t: self._fill())
        v.addWidget(self.filter)
        self.list = QListWidget(self)
        self.list.itemDoubleClicked.connect(lambda _i: self.open_selected())
        v.addWidget(self.list, 1)
        self.open_button = QPushButton("Open", self)
        self.open_button.clicked.connect(lambda _c=False: self.open_selected())
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.addButton(self.open_button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        self._fill()

    def _fill(self) -> None:
        text = self.filter.text().strip().lower()
        self.list.clear()
        shown = [d for d in self.items if text in (d["title"] + " " + d["group"]).lower()]
        for d in shown:
            it = QListWidgetItem(f"{d['title']}   [{d['group']}]")
            it.setData(256, d["path"])
            self.list.addItem(it)
        if not self.items:
            self.note.setText(f"No tutorial documents were found in\n{self.root}")
        else:
            self.note.setText(f"{len(shown)} of {len(self.items)} documents. Double-click one to open it.")
        if shown:
            self.list.setCurrentRow(0)
        self.open_button.setEnabled(bool(shown))

    def titles(self) -> List[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def open_selected(self) -> Optional[str]:
        it = self.list.currentItem()
        if it is None:
            return None
        path = it.data(256)
        self._open(path)
        return path
