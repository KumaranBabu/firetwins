"""Composite commands: atomic groups and state-swap (snapshot) commands."""
from __future__ import annotations

from typing import Any, List, Optional

from .base import Command, CommandResult


class GroupCommand(Command):
    """
    Execute multiple commands atomically as a single undo/redo unit.

    If any command fails during ``execute()``, all previously executed
    commands in the group are rolled back.

    Parameters
    ----------
    commands : list[Command]
        Commands to execute in order.
    label : str, optional
        Human-readable description for the history panel.

    Example::

        group = GroupCommand([
            AddEntityCommand(project, mesh1),
            AddEntityCommand(project, mesh2),
            ModifyPropertyCommand(project, "params.t_end", 120.0),
        ], label="add two meshes and set timing")
        pipeline.execute(group)
        pipeline.undo()   # undoes all three at once
    """
    def __init__(self, commands: List[Command], label: str = "") -> None:
        self._commands = list(commands)
        self.description = label or f"group({len(self._commands)} commands)"
        self._executed: List[Command] = []

    def execute(self) -> CommandResult:
        self._executed = []
        for cmd in self._commands:
            result = cmd.execute()
            if result.success:
                self._executed.append(cmd)
            else:
                # Roll back already-executed commands
                for done in reversed(self._executed):
                    try:
                        done.undo()
                    except Exception:
                        pass
                self._executed = []
                return CommandResult.fail(
                    f"GroupCommand aborted at '{cmd.description}': {result.message}"
                )
        return CommandResult.ok(self.description)

    def undo(self) -> CommandResult:
        for cmd in reversed(self._executed):
            result = cmd.undo()
            if not result.success:
                return CommandResult.fail(
                    f"GroupCommand undo failed at '{cmd.description}': {result.message}"
                )
        self._executed = []
        return CommandResult.ok(f"Undone: {self.description}")

    def __len__(self) -> int:
        return len(self._commands)


class StateSwapCommand(Command):
    """
    Make an arbitrary state-changing *action* undoable by snapshotting state.

    ``capture()`` returns an opaque snapshot of everything the action may
    change; ``restore(snapshot)`` puts a snapshot back. The first
    ``execute()`` runs *action* (capturing before and after); undo restores
    the "before" snapshot and redo restores the "after" snapshot instead of
    re-running the action, so redo is deterministic and cheap.

    If the action raises, the "before" snapshot is restored (no partial
    change), the command reports failure, and the original exception is kept
    in :attr:`error` so the caller can re-raise it. The action's return value
    is kept in :attr:`value`.
    """
    _UNSET = object()

    def __init__(self, label: str, capture, restore, action) -> None:
        self.description = label
        self._capture = capture
        self._restore = restore
        self._action = action
        self._before = self._UNSET
        self._after = self._UNSET
        self.value: Any = None
        self.error: Optional[BaseException] = None

    def execute(self) -> CommandResult:
        if self._after is not self._UNSET:      # redo
            try:
                self._restore(self._after)
                return CommandResult.ok(self.description)
            except Exception as exc:
                return CommandResult.fail(str(exc))
        before = self._capture()
        try:
            self.value = self._action()
        except Exception as exc:
            self._restore(before)
            self.error = exc
            return CommandResult.fail(str(exc))
        self._before = before
        self._after = self._capture()
        return CommandResult.ok(self.description)

    def undo(self) -> CommandResult:
        try:
            self._restore(self._before)
            return CommandResult.ok(f"Undid {self.description}")
        except Exception as exc:
            return CommandResult.fail(str(exc))
