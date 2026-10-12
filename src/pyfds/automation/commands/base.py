"""Command base class and result type."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandResult:
    """Returned by every ``Command.execute()`` call."""
    success: bool = True
    message: str = ""
    payload: Any = None

    @classmethod
    def ok(cls, message: str = "", payload: Any = None) -> "CommandResult":
        return cls(success=True, message=message, payload=payload)

    @classmethod
    def fail(cls, message: str) -> "CommandResult":
        return cls(success=False, message=message)


class Command:
    """
    Abstract base class for all pipeline commands.

    Subclasses must implement ``execute()`` and ``undo()``.
    The ``description`` property is used for history labelling.
    """
    description: str = "command"
    #: Who issued the command: "user", "agent", "plugin:<id>", "script" ...
    #: Stamped by the pipeline from its current actor context.
    actor: str = "user"
    #: Commands with an equal, non-None ``merge_key`` may be coalesced into
    #: one undo step when the caller opts in (see ``CommandPipeline.execute``).
    merge_key: Any = None

    def merge_with(self, other: "Command") -> bool:
        """Absorb *other* (already executed) into this command; True if merged."""
        return False

    def execute(self) -> CommandResult:
        raise NotImplementedError

    def undo(self) -> CommandResult:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.description}>"
