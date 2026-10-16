"""Mesh tools of the Edit Meshes dialog (plan step F5, MSH-02/03/06-11): the live **Division** readout (cell size, cell
counts, total cells, Poisson advice, set-by-cell-size) and the **Mesh tools** panel (split, refine, merge, partition,
move/scale/mirror/rotate, stretching, refinement zone, open boundaries). Mixed into ``EntityCollectionEditor``.

Every tool is a ``do_*`` method that takes plain values and calls ``api.meshes`` (one undo step each); the button
handlers only ask for the values (``_ask``) and report errors, so the logic can be tested without any dialog.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

AXES = ["X", "Y", "Z"]


def is_poisson(n: int) -> bool:
    """True when n = 2^a 3^b 5^c (the cell counts FDS's Poisson solver likes)."""
    if n < 1:
        return False
    for f in (2, 3, 5):
        while n % f == 0:
            n //= f
    return n == 1


def nearest_poisson(n: int) -> int:
    """The smallest Poisson-friendly count >= n."""
    n = max(1, n)
    while not is_poisson(n):
        n += 1
    return n


def poisson_counts(extent: Sequence[float], cell: float) -> Tuple[int, int, int]:
    """Cell counts that give about *cell* size on a box of the given *extent*, each rounded UP to the nearest count
    FDS's Poisson solver likes (only prime factors 2, 3, 5)."""
    if cell <= 0:
        raise ValueError("cell size must be > 0")
    return tuple(nearest_poisson(max(1, math.ceil(e / cell - 1e-9))) for e in extent)


class MeshToolsMixin:
    # -- building -----------------------------------------------------------------------------------------
    def _build_division_row(self, layout: QVBoxLayout, parent: QWidget) -> None:
        self.division_box = QGroupBox("Division", parent)
        v = QVBoxLayout(self.division_box)
        self.division_label = QLabel("", self.division_box)
        self.division_label.setWordWrap(True)
        v.addWidget(self.division_label)
        row = QHBoxLayout()
        self.cell_size_button = QPushButton("Set cell size...", self.division_box)
        self.cell_size_button.clicked.connect(lambda _c=False: self.ask_cell_size())
        self.poisson_button = QPushButton("Use nearest Poisson counts", self.division_box)
        self.poisson_button.clicked.connect(lambda _c=False: self.use_poisson_counts())
        row.addWidget(self.cell_size_button)
        row.addWidget(self.poisson_button)
        row.addStretch(1)
        v.addLayout(row)
        layout.addWidget(self.division_box)
        self.division_box.setVisible(self.attr == "meshes")

    def _build_mesh_tools(self, layout: QVBoxLayout, parent: QWidget) -> None:
        self.tools_box = QGroupBox("Mesh tools", parent)
        v = QVBoxLayout(self.tools_box)
        self.tool_buttons: Dict[str, QPushButton] = {}
        for key, text, slot in (
                ("split", "Split...", self.ask_split), ("partition", "Partition (MPI)...", self.ask_partition),
                ("refine", "Refine...", self.ask_refine), ("zone", "Refine zone...", self.ask_refine_zone),
                ("merge", "Merge...", self.ask_merge), ("transform", "Move / Scale / Mirror / Rotate...", self.ask_transform),
                ("stretch", "Stretching...", self.ask_stretching), ("open", "Open boundaries", self.open_boundaries_now)):
            b = QPushButton(text, self.tools_box)
            b.clicked.connect(lambda _c=False, s=slot: s())
            v.addWidget(b)
            self.tool_buttons[key] = b
        layout.addWidget(self.tools_box)
        self.tools_box.setVisible(self.attr == "meshes")

    # -- units and the readout ----------------------------------------------------------------------------
    def _len_label(self) -> str:
        return self.api.units.label("length")

    def _to_disp(self, si: float) -> float:
        return self.api.units.to_display(si, "length")

    def _from_disp(self, shown: float) -> float:
        return self.api.units.from_display(shown, "length")

    def pending_geometry(self) -> Optional[Tuple[List[float], List[float], Tuple[int, int, int]]]:
        """(lo, hi, cells) in SI from the form as it stands now, or None while a value is missing."""
        if self.attr != "meshes" or not self._widgets:
            return None
        try:
            vals = self.pending()
            lo = [self._from_disp(vals[f"{a}_min"]) for a in "xyz"]
            hi = [self._from_disp(vals[f"{a}_max"]) for a in "xyz"]
            cells = tuple(int(c) for c in vals["cell_count"])
        except (KeyError, TypeError, ValueError):
            return None
        return lo, hi, cells

    def division_text(self) -> str:
        geo = self.pending_geometry()
        if geo is None:
            return "(enter the bounds and cell counts to see the division)"
        lo, hi, cells = geo
        if any(c < 1 for c in cells) or any(h <= l for l, h in zip(lo, hi)):
            return "! bounds must increase and every cell count must be at least 1"
        size = [(hi[i] - lo[i]) / cells[i] for i in range(3)]
        unit = self._len_label()
        lines = ["cell size: " + " x ".join(f"{self._to_disp(s):.4g}" for s in size) + f" {unit}   "
                 f"(aspect ratio {max(size) / min(size):.2f})",
                 f"cells: {cells[0]} x {cells[1]} x {cells[2]} = {cells[0] * cells[1] * cells[2]:,}"]
        bad = [f"{AXES[i]}={cells[i]} (use {nearest_poisson(cells[i])})" for i in range(3)
               if not is_poisson(cells[i])]
        lines.append("! Poisson solver prefers counts with only factors 2, 3, 5: " + ", ".join(bad) if bad
                     else "Cell counts are Poisson-friendly.")
        if self._current is not None:
            try:
                axes = self.api.meshes.stats(self._current)["non_uniform_axes"]
                if axes:
                    lines.append("non-uniform spacing on " + ", ".join(axes))
            except Exception:
                pass
        return "\n".join(lines)

    def _refresh_division(self) -> None:
        if self.attr != "meshes":
            return
        text = self.division_text() if self._current is not None else ""
        self.division_label.setStyleSheet("color: #b3261e;" if "!" in text else "")
        self.division_label.setText(text)

    def set_cell_size(self, dx: float, dy: Optional[float] = None, dz: Optional[float] = None,
                      poisson: bool = True) -> Tuple[int, int, int]:
        """Put cell counts for the wanted size (display units) into the form; saved by Apply/OK."""
        geo = self.pending_geometry()
        if geo is None:
            raise ValueError("enter the mesh bounds first")
        lo, hi, _ = geo
        sizes = [self._from_disp(s) for s in (dx, dy if dy is not None else dx, dz if dz is not None else dx)]
        counts = []
        for i in range(3):
            if sizes[i] <= 0:
                raise ValueError("cell size must be > 0")
            n = max(1, math.ceil((hi[i] - lo[i]) / sizes[i] - 1e-9))
            counts.append(nearest_poisson(n) if poisson else n)
        self._widgets["cell_count"].set_value(tuple(counts))
        return tuple(counts)

    def use_poisson_counts(self) -> Tuple[int, int, int]:
        geo = self.pending_geometry()
        if geo is None:
            raise ValueError("enter the mesh bounds and cell counts first")
        counts = tuple(nearest_poisson(max(1, c)) for c in geo[2])
        self._widgets["cell_count"].set_value(counts)
        return counts

    def ask_cell_size(self) -> Optional[Tuple[int, int, int]]:
        geo = self.pending_geometry()
        if geo is None:
            return None
        size = [self._to_disp((geo[1][i] - geo[0][i]) / max(1, geo[2][i])) for i in range(3)]
        got = self._ask("Set Cell Size", [("size", f"Cell size ({self._len_label()})", "float", size[0]),
                                          ("poisson", "Round counts to Poisson-friendly", "bool", True)])
        if got is None:
            return None
        return self._guard(lambda: self.set_cell_size(got["size"], poisson=got["poisson"]))

    # -- the tools (logic) ---------------------------------------------------------------------------------
    def _mesh_op(self, fn):
        """Save pending edits, run *fn(manager)* and show the outcome; raises ValueError/KeyError on a refusal."""
        if self._current is not None and not self._apply_quietly():
            raise ValueError("fix the highlighted values first")
        result = fn(self.api.meshes)
        keep = self._current.name if self._current is not None and self.api.meshes.get(self._current.name) else None
        self._current = None
        self.refresh_list(keep)
        return result

    def do_split(self, axis: str, at: Optional[float] = None) -> Any:
        """Cut the current mesh at *at* (display units; None = middle). Returns the new mesh."""
        mesh = self._current
        if mesh is None:
            raise ValueError("select a mesh first")
        pos = None if at is None else self._from_disp(at)
        return self._mesh_op(lambda m: m.split(mesh, axis, pos))

    def do_partition(self, parts: int, axis: Optional[str] = None) -> List[Any]:
        mesh = self._current
        if mesh is None:
            raise ValueError("select a mesh first")
        return self._mesh_op(lambda m: m.partition(mesh, parts, axis))

    def do_refine(self, factor: int) -> Any:
        mesh = self._current
        if mesh is None:
            raise ValueError("select a mesh first")
        return self._mesh_op(lambda m: m.refine(mesh, factor))

    def do_refine_zone(self, xb_display: Sequence[float], factor: int) -> List[Any]:
        mesh = self._current
        if mesh is None:
            raise ValueError("select a mesh first")
        xb = [self._from_disp(v) for v in xb_display]
        return self._mesh_op(lambda m: m.apply_refinement(mesh, xb, factor))

    def do_merge(self, names: Sequence[str]) -> Any:
        return self._mesh_op(lambda m: m.merge(list(names)))

    def do_transform(self, op: str, **kw) -> Any:
        """op: move (dx, dy, dz) | scale (factor) | mirror (axis, at, copy) | rotate (angle, copy). Lengths in display units."""
        mesh = self._current
        if mesh is None:
            raise ValueError("select a mesh first")
        f = self._from_disp
        if op == "move":
            return self._mesh_op(lambda m: m.move(mesh, f(kw.get("dx", 0.0)), f(kw.get("dy", 0.0)), f(kw.get("dz", 0.0))))
        if op == "scale":
            return self._mesh_op(lambda m: m.scale(mesh, kw["factor"]))
        if op == "mirror":
            return self._mesh_op(lambda m: m.mirror(mesh, kw["axis"], f(kw["at"]), copy=kw.get("copy", False)))
        if op == "rotate":
            return self._mesh_op(lambda m: m.rotate(mesh, kw["angle"], copy=kw.get("copy", False)))
        raise ValueError(f"unknown transform {op!r}")

    def do_stretching(self, axis: str, points: Sequence[Tuple[float, float]]) -> List[Any]:
        """*points* = [(coordinate in display units, fraction of cells below it 0..1)]; empty = uniform again."""
        mesh = self._current
        if mesh is None:
            raise ValueError("select a mesh first")
        pts = [(self._from_disp(cc), pc) for cc, pc in points]
        return self._mesh_op(lambda m: m.set_stretching(mesh, axis, pts))

    def do_open_boundaries(self, surf_id: str = "OPEN") -> List[Any]:
        return self._mesh_op(lambda m: m.open_boundaries(surf_id))

    # -- the tools (buttons) --------------------------------------------------------------------------------
    def _ask(self, title: str, fields: List[tuple]) -> Optional[Dict[str, Any]]:
        """Small parameter dialog. fields: (key, label, kind, default[, choices]); kinds: float, int, bool, choice, text."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        form = QFormLayout(dlg)
        inputs: Dict[str, Any] = {}
        for f in fields:
            key, label, kind, default = f[:4]
            if kind == "float":
                w = QDoubleSpinBox(dlg)
                w.setDecimals(4)
                w.setRange(-1e9, 1e9)
                w.setValue(float(default or 0.0))
            elif kind == "int":
                w = QSpinBox(dlg)
                w.setRange(-10 ** 6, 10 ** 6)
                w.setValue(int(default or 0))
            elif kind == "bool":
                from PySide6.QtWidgets import QCheckBox
                w = QCheckBox(dlg)
                w.setChecked(bool(default))
            elif kind == "choice":
                w = QComboBox(dlg)
                w.addItems(list(f[4]))
                w.setCurrentText(str(default))
            else:
                w = QLineEdit(dlg)
                w.setText(str(default or ""))
            inputs[key] = (kind, w)
            form.addRow(label, w)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted:
            return None
        out: Dict[str, Any] = {}
        for key, (kind, w) in inputs.items():
            out[key] = (w.isChecked() if kind == "bool" else w.currentText() if kind == "choice"
                        else w.text() if kind == "text" else w.value())
        return out

    def _guard(self, fn):
        try:
            return fn()
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return None

    def _extent_display(self, axis: str) -> Tuple[float, float]:
        m, i = self._current, AXES.index(axis)
        return (self._to_disp(getattr(m, f"{'xyz'[i]}_min")), self._to_disp(getattr(m, f"{'xyz'[i]}_max")))

    def ask_split(self) -> Any:
        if self._current is None:
            return None
        got = self._ask("Split Mesh", [("axis", "Cut plane perpendicular to", "choice", "X", AXES),
                                       ("at", f"Position ({self._len_label()}), blank = middle", "text", "")])
        if got is None:
            return None
        try:
            at = float(got["at"].replace(",", ".")) if got["at"].strip() else None
        except ValueError:
            QMessageBox.warning(self, "Split Mesh", "position must be a number")
            return None
        return self._guard(lambda: self.do_split(got["axis"], at))

    def ask_partition(self) -> Any:
        if self._current is None:
            return None
        got = self._ask("Partition Mesh", [("parts", "Number of parts (one per MPI process)", "int", 2),
                                           ("axis", "Along", "choice", "Longest", ["Longest"] + AXES)])
        if got is None:
            return None
        return self._guard(lambda: self.do_partition(got["parts"], None if got["axis"] == "Longest" else got["axis"]))

    def ask_refine(self) -> Any:
        if self._current is None:
            return None
        got = self._ask("Refine Mesh", [("factor", "Divide every cell by (2 = one cell becomes eight)", "int", 2)])
        return None if got is None else self._guard(lambda: self.do_refine(got["factor"]))

    def ask_refine_zone(self) -> Any:
        if self._current is None:
            return None
        fields = []
        for a in AXES:
            lo, hi = self._extent_display(a)
            fields += [(f"{a}0", f"{a} from ({self._len_label()})", "float", lo), (f"{a}1", f"{a} to", "float", hi)]
        got = self._ask("Refine Zone", fields + [("factor", "Refine by", "int", 2)])
        if got is None:
            return None
        xb = [got[f"{a}{k}"] for a in AXES for k in (0, 1)]
        return self._guard(lambda: self.do_refine_zone(xb, got["factor"]))

    def ask_merge(self) -> Any:
        names = self.names()
        if len(names) < 2:
            QMessageBox.information(self, "Merge Meshes", "There is only one mesh.")
            return None
        got = self._ask("Merge Meshes", [("a", "First mesh (kept)", "choice", self._current.name if self._current else names[0], names),
                                         ("b", "Merge in", "choice", next((n for n in names if self._current is None or n != self._current.name), names[0]), names)])
        return None if got is None else self._guard(lambda: self.do_merge([got["a"], got["b"]]))

    def ask_transform(self) -> Any:
        if self._current is None:
            return None
        u = self._len_label()
        got = self._ask("Transform Mesh", [
            ("op", "Operation", "choice", "move", ["move", "scale", "mirror", "rotate"]),
            ("dx", f"Move dx ({u})", "float", 0.0), ("dy", "Move dy", "float", 0.0), ("dz", "Move dz", "float", 0.0),
            ("factor", "Scale factor (about the origin)", "float", 1.0),
            ("axis", "Mirror across plane perpendicular to", "choice", "X", AXES), ("at", f"Mirror plane position ({u})", "float", 0.0),
            ("angle", "Rotate degrees (multiples of 90, about the origin)", "float", 90.0),
            ("copy", "Mirror/rotate a copy instead of moving", "bool", False)])
        if got is None:
            return None
        kw = {"move": {k: got[k] for k in ("dx", "dy", "dz")}, "scale": {"factor": got["factor"]},
              "mirror": {"axis": got["axis"], "at": got["at"], "copy": got["copy"]},
              "rotate": {"angle": got["angle"], "copy": got["copy"]}}[got["op"]]
        return self._guard(lambda: self.do_transform(got["op"], **kw))

    def ask_stretching(self) -> Any:
        if self._current is None:
            return None
        got = self._ask("Mesh Stretching", [
            ("axis", "Axis", "choice", "X", AXES),
            ("points", f"Control points 'coordinate:fraction' ({self._len_label()}), comma separated; blank = uniform",
             "text", "")])
        if got is None:
            return None
        try:
            pts = [tuple(float(x) for x in p.split(":")) for p in got["points"].replace(";", ",").split(",") if p.strip()]
            if any(len(p) != 2 for p in pts):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Mesh Stretching", "write each point as coordinate:fraction, e.g. 1.5:0.8")
            return None
        return self._guard(lambda: self.do_stretching(got["axis"], pts))

    def open_boundaries_now(self) -> Any:
        made = self._guard(self.do_open_boundaries)
        if made is not None:
            QMessageBox.information(self, "Open Boundaries", f"{len(made)} open vent(s) added." if made
                                    else "Every outer face already has an open vent.")
        return made
