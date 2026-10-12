"""A small generic editor for the viewer's settings dataclasses (preferences panels, colorbar, smoke, units...).

``SettingsDialog`` builds one widget per dataclass field: a checkbox for bool, a spin box for int / float, a
combo box when *choices* names the allowed values, a line edit otherwise. ``values()`` returns only the
fields the user changed, ready to hand to the matching ``api.viewer.set_*`` call (which validates them).
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
                               QLineEdit, QSpinBox, QVBoxLayout, QWidget)


def _title(name: str) -> str:
    return name.replace("_", " ").capitalize()


class SettingsDialog(QDialog):
    def __init__(self, title: str, obj: Any, parent: Optional[QWidget] = None,
                 choices: Optional[Mapping[str, Sequence[str]]] = None, hide: Sequence[str] = (), note: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._obj = obj
        self._widgets: Dict[str, Tuple[QWidget, type]] = {}
        lay = QVBoxLayout(self)
        if note:
            lab = QLabel(note)
            lab.setWordWrap(True)
            lay.addWidget(lab)
        form = QFormLayout()
        lay.addLayout(form)
        for f in dataclasses.fields(obj):
            if f.name in hide:
                continue
            cur = getattr(obj, f.name)
            w = self._make(f.name, cur, (choices or {}).get(f.name))
            if w is None:
                continue
            form.addRow(_title(f.name), w[0])
            self._widgets[f.name] = w
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _make(self, name: str, cur: Any, choices: Optional[Sequence[str]]):
        if choices:
            c = QComboBox()
            c.addItems(list(choices))
            if str(cur) in choices:
                c.setCurrentText(str(cur))
            return c, str
        if isinstance(cur, bool):
            c = QCheckBox()
            c.setChecked(cur)
            return c, bool
        if isinstance(cur, int):
            s = QSpinBox()
            s.setRange(-10 ** 9, 10 ** 9)
            s.setValue(cur)
            return s, int
        if isinstance(cur, float):
            d = QDoubleSpinBox()
            d.setDecimals(4)
            d.setRange(-1e12, 1e12)
            d.setValue(cur)
            return d, float
        if cur is None or isinstance(cur, str):
            e = QLineEdit("" if cur is None else cur)
            return e, str
        return None                                            # lists / nested objects: edited elsewhere

    def values(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name, (w, kind) in self._widgets.items():
            cur = getattr(self._obj, name)
            if isinstance(w, QComboBox):
                new: Any = w.currentText()
            elif isinstance(w, QCheckBox):
                new = w.isChecked()
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                new = w.value()
            else:
                text = w.text().strip()
                new = text if text or cur is not None else None
                if cur is None and not text:
                    new = None
            if new != cur and not (cur is None and new in ("", None)):
                out[name] = new
        return out
