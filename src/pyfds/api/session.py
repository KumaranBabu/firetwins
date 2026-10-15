"""
PyFDS Session Manager
=====================
A ``Session`` wraps a live ``FdsProject`` together with its on-disk path,
dirty-tracking, undo/redo history, and auto-save state.

``SessionManager`` handles multiple concurrent sessions (e.g., two scenarios
open side-by-side in a future tabbed GUI).

All persistence is delegated to ``pyfds.io.serializer.Serializer``; this
module only tracks lifecycle state.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class Session:
    """
    Represents one open PyFDS project.

    Attributes
    ----------
    session_id : str
        Globally unique identifier for this session.
    project : FdsProject
        The live domain model. May be replaced on ``load()``.
    filepath : Optional[Path]
        Where the project was last saved / loaded from.
    is_dirty : bool
        True when there are unsaved changes.
    created_at : float
        monotonic timestamp of session creation.
    """

    def __init__(self, project: Any, filepath: Optional[str] = None) -> None:
        self.session_id: str = str(uuid.uuid4())
        self.project: Any = project
        self.filepath: Optional[Path] = Path(filepath) if filepath else None
        self.is_dirty: bool = False
        self.created_at: float = time.monotonic()
        self._last_saved_at: Optional[float] = None
        self._auto_save_interval: Optional[float] = None   # seconds, None = disabled
        self._auto_save_thread: Optional[threading.Thread] = None
        self._auto_save_stop = threading.Event()
        self._on_auto_save_callbacks: List[Any] = []

    # ── Dirty tracking ───────────────────────────────────────────────────────

    def mark_dirty(self) -> None:
        self.is_dirty = True

    def mark_clean(self) -> None:
        self.is_dirty = False
        self._last_saved_at = time.monotonic()

    # ── File management ───────────────────────────────────────────────────────

    def save(self, filepath: Optional[str] = None) -> Path:
        """
        Persist the project to *filepath* (or the existing ``self.filepath``).

        Delegates actual I/O to the Serializer; raises ``FdsSerializationError``
        on failure.  Updates ``filepath``, clears dirty flag.
        """
        from pyfds.io.serializer import Serializer
        target = Path(filepath) if filepath else self.filepath
        if target is None:
            raise ValueError("No filepath specified and session has no prior path.")
        target = target.with_suffix(".pyfds")
        Serializer().save(self.project, str(target))
        self.filepath = target
        from pyfds.io.recovery import discard_autosave
        discard_autosave(target)
        self.mark_clean()
        logger.info("Session[%s] saved to %s", self.session_id[:8], target)
        return target

    def load(self, filepath: str) -> None:
        """
        Replace ``self.project`` with a freshly parsed project from *filepath*.

        Accepts both raw `.fds` namelists and `.pyfds` JSON archives.
        """
        from pyfds.io.serializer import Serializer
        from pyfds.io.fds_parser import FdsParser
        path = Path(filepath)
        if path.suffix.lower() == ".pyfds":
            self.project = Serializer().load(filepath)
        else:
            self.project = FdsParser().parse(filepath)
        self.filepath = path
        self.mark_clean()
        logger.info("Session[%s] loaded from %s", self.session_id[:8], path)

    # ── Auto-save ────────────────────────────────────────────────────────────

    def enable_auto_save(self, interval_seconds: float = 300.0) -> None:
        """Start a background thread that saves the session every *interval* seconds."""
        if self._auto_save_thread and self._auto_save_thread.is_alive():
            return
        self._auto_save_interval = interval_seconds
        self._auto_save_stop.clear()
        self._auto_save_thread = threading.Thread(
            target=self._auto_save_loop,
            daemon=True,
            name=f"pyfds-autosave-{self.session_id[:8]}",
        )
        self._auto_save_thread.start()
        logger.debug("Auto-save enabled every %.0fs for session %s",
                     interval_seconds, self.session_id[:8])

    def disable_auto_save(self) -> None:
        """Stop the auto-save background thread."""
        self._auto_save_stop.set()

    def _auto_save_loop(self) -> None:
        while not self._auto_save_stop.wait(timeout=self._auto_save_interval):
            if self.is_dirty and self.filepath:
                try:
                    from pyfds.io.recovery import write_autosave
                    write_autosave(self.project, self.filepath)
                    logger.info("Auto-saved session %s", self.session_id[:8])
                except Exception as exc:
                    logger.error("Auto-save failed: %s", exc)

    # ── Metadata ─────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "filepath": str(self.filepath) if self.filepath else None,
            "is_dirty": self.is_dirty,
            "created_at": self.created_at,
            "last_saved_at": self._last_saved_at,
            "chid": getattr(self.project, "chid", ""),
            "title": getattr(self.project, "title", ""),
        }

    def __repr__(self) -> str:
        dirty = " [dirty]" if self.is_dirty else ""
        path = str(self.filepath) if self.filepath else "<unsaved>"
        return f"<Session id={self.session_id[:8]} path={path!r}{dirty}>"


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class SessionManager:
    """
    Manages a pool of open ``Session`` objects.

    The concept maps directly to an "open files" manager in a future tabbed
    GUI — each tab is a Session. Headless scripts typically have exactly one.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._active_id: Optional[str] = None
        self._lock = threading.Lock()

    # ── Session lifecycle ────────────────────────────────────────────────────

    def new_session(self, project: Any, filepath: Optional[str] = None) -> Session:
        """Create and register a new session, making it the active one."""
        session = Session(project, filepath)
        with self._lock:
            self._sessions[session.session_id] = session
            self._active_id = session.session_id
        logger.debug("SessionManager: new session %s", session.session_id[:8])
        return session

    def open(self, filepath: str) -> Session:
        """
        Load a project from *filepath* into a new session.

        Accepts `.fds` or `.pyfds` files.  Returns the new active session.
        """
        from pyfds.domain.model import FdsProject
        session = self.new_session(FdsProject())
        session.load(filepath)
        return session

    def close(self, session_id: str, force: bool = False) -> None:
        """
        Close a session.

        Parameters
        ----------
        session_id : str
            The ID of the session to close.
        force : bool
            If False and the session is dirty, raises ``RuntimeError``.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            if session.is_dirty and not force:
                raise RuntimeError(
                    f"Session {session_id[:8]} has unsaved changes. "
                    "Pass force=True to discard."
                )
            session.disable_auto_save()
            del self._sessions[session_id]
            if self._active_id == session_id:
                # Activate the most-recently-created remaining session
                remaining = list(self._sessions.values())
                self._active_id = remaining[-1].session_id if remaining else None
        logger.debug("SessionManager: closed session %s", session_id[:8])

    def close_all(self, force: bool = True) -> None:
        """Close all open sessions."""
        for sid in list(self._sessions.keys()):
            self.close(sid, force=force)

    # ── Access ───────────────────────────────────────────────────────────────

    @property
    def active(self) -> Optional[Session]:
        """The currently active session."""
        if self._active_id:
            return self._sessions.get(self._active_id)
        return None

    def set_active(self, session_id: str) -> None:
        """Switch the active session."""
        if session_id not in self._sessions:
            raise KeyError(f"No session with id {session_id!r}")
        self._active_id = session_id

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    @property
    def all_sessions(self) -> List[Session]:
        return list(self._sessions.values())

    @property
    def count(self) -> int:
        return len(self._sessions)

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def status(self) -> List[Dict[str, Any]]:
        """Return a list of session metadata dicts (safe for GUI display)."""
        return [s.to_dict() for s in self._sessions.values()]

    def __repr__(self) -> str:
        active = self._active_id[:8] if self._active_id else "none"
        return f"<SessionManager sessions={self.count} active={active}>"
