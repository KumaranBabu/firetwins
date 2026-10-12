"""``CommandPipeline`` — the per-document undo/redo history and transaction stack."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import Command, CommandResult
from .group import GroupCommand

logger = logging.getLogger(__name__)


@dataclass
class _TxFrame:
    label: str
    actor: str
    commands: List[Command] = field(default_factory=list)


class CommandPipeline:
    """
    Maintains an undo/redo history of executed commands.

    Parameters
    ----------
    project : FdsProject, optional
        Stored for context; not required by the pipeline itself.
    max_history : int
        Maximum undo stack depth (default: 200).

    Example::

        pipe = CommandPipeline(project, max_history=100)
        result = pipe.execute(AddEntityCommand(project, mesh))
        pipe.undo()
        pipe.redo()
        print(pipe.history_labels())
    """

    def __init__(self, project=None, max_history: int = 200) -> None:
        self.project     = project
        self._max        = max_history
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._actor: str = "user"
        self._tx: List["_TxFrame"] = []          # open transactions (innermost last)
        self._coalescing: Optional[Command] = None

    def execute(self, command: Command, coalesce: bool = False) -> CommandResult:
        """
        Execute *command*, push it to the undo stack, clear the redo stack.

        Inside :meth:`transaction` the command runs immediately but is only
        recorded when the transaction commits (as one grouped step).

        With ``coalesce=True`` a command that has the same ``merge_key`` as
        the previous coalescing command is merged into it, so a drag or a
        spin-box edit session becomes ONE undo step. Call :meth:`seal` (or
        any other command/undo/redo) to end a coalescing run.

        Returns the ``CommandResult`` from the command.
        """
        command.actor = self._actor
        result = command.execute()
        if not result.success:
            logger.warning("CommandPipeline: command failed: %s — %s",
                           command, result.message)
            return result
        if self._tx:
            self._tx[-1].commands.append(command)
            self._coalescing = None
            return result
        top = self._undo_stack[-1] if self._undo_stack else None
        if (coalesce and top is not None and top is self._coalescing
                and top.merge_key is not None and top.merge_key == command.merge_key
                and top.merge_with(command)):
            self._redo_stack.clear()
            self._emit_event("COMMAND_EXECUTED", top)
            return result
        self._push(command)
        self._coalescing = command if coalesce else None
        logger.debug("CommandPipeline: executed %s", command)
        return result

    def _push(self, command: Command) -> None:
        self._undo_stack.append(command)
        if len(self._undo_stack) > self._max:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._emit_event("COMMAND_EXECUTED", command)

    # ── Transactions / actor / coalescing ─────────────────────────────────────

    @contextmanager
    def transaction(self, label: str = "transaction", actor: Optional[str] = None):
        """
        Group everything executed inside the ``with`` block into ONE undo step.

        If the block raises, every command executed so far is undone (in
        reverse order) and the exception propagates, so no partial change and
        no history entry remain. Transactions nest; an inner one joins its
        parent. Undo/redo are refused while a transaction is open.
        """
        prev_actor = self._actor
        if actor:
            self._actor = actor
        frame = _TxFrame(label=label, actor=self._actor)
        self._tx.append(frame)
        try:
            yield frame
        except BaseException:
            self._tx.pop()
            for done in reversed(frame.commands):
                try:
                    done.undo()
                except Exception:           # keep unwinding
                    logger.exception("CommandPipeline: rollback of %s failed", done)
            self._actor = prev_actor
            raise
        self._tx.pop()
        self._actor = prev_actor
        if not frame.commands:
            return
        if self._tx:                            # nested: join the parent
            self._tx[-1].commands.extend(frame.commands)
            return
        group = GroupCommand(frame.commands, label=label)
        group._executed = list(frame.commands)  # already executed
        group.actor = frame.actor
        self._coalescing = None
        self._push(group)

    @contextmanager
    def actor(self, name: str):
        """Attribute commands executed inside the block to *name*."""
        prev, self._actor = self._actor, name
        try:
            yield
        finally:
            self._actor = prev

    def seal(self) -> None:
        """End the current coalescing run (next edit starts a new undo step)."""
        self._coalescing = None

    def undo(self) -> Optional[CommandResult]:
        """
        Undo the most recent command.

        Returns ``CommandResult`` or None if the stack is empty.
        """
        self._refuse_in_transaction("undo")
        self._coalescing = None
        if not self._undo_stack:
            logger.debug("CommandPipeline: undo stack is empty")
            return None
        command = self._undo_stack.pop()
        result  = command.undo()
        if result.success:
            self._redo_stack.append(command)
            self._emit_event("UNDO_PERFORMED", command)
            logger.debug("CommandPipeline: undone %s", command)
        else:
            # Push back — the undo failed, keep state consistent
            self._undo_stack.append(command)
            logger.error("CommandPipeline: undo failed: %s", result.message)
        return result

    def redo(self) -> Optional[CommandResult]:
        """
        Re-apply the most recently undone command.

        Returns ``CommandResult`` or None if the redo stack is empty.
        """
        self._refuse_in_transaction("redo")
        self._coalescing = None
        if not self._redo_stack:
            logger.debug("CommandPipeline: redo stack is empty")
            return None
        command = self._redo_stack.pop()
        result  = command.execute()
        if result.success:
            self._undo_stack.append(command)
            self._emit_event("REDO_PERFORMED", command)
            logger.debug("CommandPipeline: redone %s", command)
        else:
            self._redo_stack.append(command)
            logger.error("CommandPipeline: redo failed: %s", result.message)
        return result

    def clear_history(self) -> None:
        """Discard all undo and redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._coalescing = None
        self._emit_event("HISTORY_CLEARED", None)

    # ── Introspection ──────────────────────────────────────────────────────────

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def history_labels(self) -> List[str]:
        """Human-readable list of undoable command descriptions (oldest first)."""
        return [c.description for c in self._undo_stack]

    def history_entries(self) -> List[Dict[str, str]]:
        """Undoable commands (oldest first) as ``{"label", "actor"}`` dicts."""
        return [{"label": c.description, "actor": c.actor} for c in self._undo_stack]

    def redo_labels(self) -> List[str]:
        return [c.description for c in reversed(self._redo_stack)]

    def __repr__(self) -> str:
        return (f"<CommandPipeline undo={len(self._undo_stack)} "
                f"redo={len(self._redo_stack)}>")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _refuse_in_transaction(self, what: str) -> None:
        if self._tx:
            raise RuntimeError(f"Cannot {what} while a transaction is open")

    def _emit_event(self, event_name: str, payload: Any) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            etype = getattr(EventType, event_name, None)
            if etype:
                get_global_bus().emit(etype, payload, source="CommandPipeline")
        except Exception:
            pass
