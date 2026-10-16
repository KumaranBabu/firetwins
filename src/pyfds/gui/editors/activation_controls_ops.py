"""List buttons and driven-object operations of the Edit Activation Controls dialog (mixed into it): new, clone,
rename, delete, and the objects a control switches."""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox


class ControlOperationsMixin:
    # -- list buttons ---------------------------------------------------------------------------------------------
    def _ask(self, title: str, label: str, text: str = "") -> Optional[str]:
        name, ok = QInputDialog.getText(self, title, label, text=text)
        return name.strip() if ok and name.strip() else None

    def _guard(self, fn):
        try:
            return fn()
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return None

    def new_control(self, name: Optional[str] = None) -> Any:
        if self._current is not None and not self._apply_quietly():
            return None
        c = self._guard(lambda: self.api.controls.create_default(name))
        if c is not None:
            self._current = None
            self.refresh_list(c.name)
        return c

    def clone_control(self, new_name: Optional[str] = None) -> Any:
        if self._current is None or not self._apply_quietly():
            return None
        src = self._current
        name = new_name or self._ask("Clone Control", "Name of the copy:", f"{src.name}_copy")
        if not name:
            return None
        def make():
            with self.api.history.transaction(f"clone control {src.name}"):
                fresh = self.api.controls.create_default(name)
                fields = {k: getattr(src, k) for k in ("function_type", "delay", "latch", "initial_state", "on_bound", "n",
                                                       "setpoint", "constant", "deadband", "percentile_rank", "ramp_id")}
                self.api.controls.update(fresh, **fields)
                if self.api.controls.inputs_of(src):
                    self.api.controls.set_inputs(fresh, self.api.controls.inputs_of(src))
            return fresh
        fresh = self._guard(make)
        if fresh is not None:
            self._current = None
            self.refresh_list(fresh.name)
        return fresh

    def rename_control(self, new_name: Optional[str] = None) -> Any:
        if self._current is None or not self._apply_quietly():
            return None
        new = new_name or self._ask("Rename Control", "New name (objects that use it follow):", self._current.name)
        if not new or new == self._current.name:
            return None
        c = self._guard(lambda: self.api.controls.rename(self._current, new))
        if c is not None:
            self._current = None
            self.refresh_list(new)
        return c

    def delete_control(self, confirm: bool = True) -> bool:
        c = self._current
        if c is None:
            return False
        users = self.api.controls.controlled(c)
        followers = self.api.controls.used_as_input(c)
        if confirm:
            extra = f"\n{len(users)} object(s) will no longer be switched by it." if users else ""
            extra += f"\n{len(followers)} control(s) lose an input." if followers else ""
            if QMessageBox.question(self, "Delete", f"Delete control {c.name}?{extra}") != QMessageBox.Yes:
                return False
        with self.api.history.transaction(f"delete control {c.name}"):
            for _k, e in users:
                self.api.controls.unassign(e)
            for o in followers:
                self.api.controls.set_inputs(o, [n for n in self.api.controls.inputs_of(o) if n != c.name])
            self.api.controls.remove(c)
        self._current = None
        self.refresh_list()
        return True

    # -- objects driven by the control -----------------------------------------------------------------------------
    def add_object(self, entity: Any) -> None:
        if self._current is None:
            raise ValueError("select a control first")
        self.api.controls.assign(self._current, entity)
        self._load_objects(self._current)

    def add_object_dialog(self) -> bool:
        if self._current is None:
            return False
        free = [(k, e) for k, e in self.api.controls.assignable() if getattr(e, "ctrl_id", None) != self._current.name]
        if not free:
            QMessageBox.information(self, self.windowTitle(), "There is nothing else that a control can switch.")
            return False
        labels = [f"{e.name}  ({k})" for k, e in free]
        label, ok = QInputDialog.getItem(self, "Add Object", "Object:", labels, 0, False)
        if not ok:
            return False
        return self._guard(lambda: self.add_object(free[labels.index(label)][1]) or True) is True

    def remove_selected_objects(self) -> int:
        items = self.driven.selectedItems()
        for it in items:
            self.api.controls.unassign(it.data(Qt.UserRole))
        if items and self._current is not None:
            self._load_objects(self._current)
        return len(items)
