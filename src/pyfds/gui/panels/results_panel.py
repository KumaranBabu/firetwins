"""Results panel: the Smokeview result sets found in the last run folder, one click to open them in the viewer."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

_PATTERNS = ("*.smv",)


def find_result_sets(folder: Optional[str]) -> List[Path]:
    """Result files (``.smv`` Smokeview index) in *folder* and one level below."""
    if not folder or not Path(folder).is_dir():
        return []
    root = Path(folder)
    found = set()
    for pat in _PATTERNS:
        found.update(root.glob(pat))
        found.update(root.glob(f"*/{pat}"))
    return sorted(found)


class ResultsPanel(QWidget):
    def __init__(self, folder_provider: Callable[[], Optional[str]], open_smv: Callable[[str], None], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._folder = folder_provider
        self._open_smv = open_smv
        root = QVBoxLayout(self)
        self.note = QLabel("")
        root.addWidget(self.note)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self.open_selected())
        root.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self.open_button = QPushButton("Open in Results Viewer")
        self.open_button.clicked.connect(self.open_selected)
        row.addWidget(refresh)
        row.addWidget(self.open_button)
        root.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        folder = self._folder()
        self.list.clear()
        sets = find_result_sets(folder)
        for path in sets:
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(str(path))
            self.list.addItem(item)
        self.note.setText(f"Results in {folder}" if sets else "No results found yet - run a simulation first.")
        self.open_button.setEnabled(bool(sets))
        if sets:
            self.list.setCurrentRow(0)

    def open_selected(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self._open_smv(item.data(Qt.UserRole))
