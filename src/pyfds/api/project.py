"""Project-level services: templates, undo/redo history, multi-document session.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class TemplateManager:
    """Apply built-in and plugin-contributed scenario presets."""

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    def list_presets(self) -> List[str]:
        from pyfds.domain.presets import list_presets
        from pyfds.plugins.loader import get_registry
        builtin  = list_presets()
        plugin   = [t.name for t in get_registry().get_scenario_templates()]
        return sorted(set(builtin + plugin))

    def apply(self, preset_name: str, **kwargs) -> None:
        """
        Apply a preset to the current api project.

        Built-in presets return a new FdsProject; this method replaces
        ``api.project`` with the returned instance.  Plugin presets that
        mutate an existing project in-place are also supported.
        """
        from pyfds.domain.presets import apply_preset, list_presets
        # Try built-in first
        if preset_name in list_presets():
            new_project = apply_preset(preset_name, **kwargs)
            self._api._project = new_project
            self._api._rebind_managers()
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(
                EventType.PROJECT_LOADED,
                {"preset_name": preset_name},
                source="TemplateManager",
            )
            return
        # Try plugin templates
        from pyfds.plugins.loader import get_registry
        for tmpl in get_registry().get_scenario_templates():
            if tmpl.name == preset_name:
                tmpl.apply(self._api.project, **kwargs)
                return
        raise KeyError(f"Preset {preset_name!r} not found")


class HistoryManager:
    """Undo/redo command pipeline."""

    def __init__(self, api: "FdsApi") -> None:
        self._api  = api
        # One CommandPipeline per open document, keyed by id(project). The
        # project is kept in the value so a recycled id() can never alias
        # a different project (the identity check in ``_pipe``).
        self._pipes: Dict[int, Any] = {}

    @property
    def _pipe(self):
        """The undo/redo pipeline of the *active* project."""
        from pyfds.automation.commands import CommandPipeline
        project = self._api.project
        entry = self._pipes.get(id(project))
        if entry is None or entry[0] is not project:
            entry = (project, CommandPipeline(project=project, max_history=200))
            self._pipes[id(project)] = entry
        return entry[1]

    def prune(self, open_projects) -> None:
        """Drop the history of documents that are no longer open."""
        keep = {id(p) for p in open_projects if p is not None}
        for key in [k for k in self._pipes if k not in keep]:
            del self._pipes[key]

    def execute(self, command: Any, coalesce: bool = False) -> Any:
        return self._pipe.execute(command, coalesce=coalesce)

    def transaction(self, label: str = "transaction", actor: Optional[str] = None):
        """Context manager: everything inside is ONE undo step (rolled back on error)."""
        return self._pipe.transaction(label, actor)

    def actor(self, name: str):
        """Context manager: attribute commands inside the block to *name*."""
        return self._pipe.actor(name)

    def seal(self) -> None:
        """End the current coalescing run."""
        self._pipe.seal()

    def entries(self) -> List[Dict[str, str]]:
        """Undoable steps as ``{"label", "actor"}`` dicts (oldest first)."""
        return self._pipe.history_entries()

    def undo(self) -> Optional[Any]:
        return self._pipe.undo()

    def redo(self) -> Optional[Any]:
        return self._pipe.redo()

    def can_undo(self) -> bool:
        return self._pipe.can_undo()

    def can_redo(self) -> bool:
        return self._pipe.can_redo()

    def history(self) -> List[str]:
        return self._pipe.history_labels()

    def clear(self) -> None:
        self._pipe.clear_history()


class SessionManager:
    """
    Multi-document project session manager.

    Maintains a registry of open projects keyed by *chid*.  One project is
    designated *active* at a time; ``FdsApi.project`` always returns the
    active project.

    Usage::

        api = FdsApi()
        api.session.open_project("building.fds")
        api.session.new_project(chid="atrium")
        api.session.switch_project("building")   # switch by chid
        print(api.session.project_list())        # ["building", "atrium"]
        api.session.close_project("atrium")
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api
        # chid → FdsProject
        self._projects: Dict[str, Any] = {}
        # Register the initial project
        p = api._project
        chid = getattr(p, "chid", "default")
        self._projects[chid] = p
        self._active_chid: str = chid

    # ── Active project ────────────────────────────────────────────────────────

    @property
    def active_project(self) -> Any:
        return self._projects[self._active_chid]

    @property
    def active_chid(self) -> str:
        return self._active_chid

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def new_project(self, chid: str = "pyfds_case", title: str = "") -> Any:
        """
        Create a blank project, add it to the session, and make it active.

        Returns the new ``FdsProject``.
        """
        from pyfds.domain.model import FdsProject
        p = FdsProject(chid=chid, title=title)
        self._projects[chid] = p
        self._activate(chid)
        logger.info("SessionManager: created new project %r", chid)
        return p

    def open_project(self, filepath: str) -> Any:
        """
        Load a project from *filepath* (``.fds`` or ``.pyfds``), register it,
        and make it active.

        Returns the loaded ``FdsProject``.
        """
        path   = Path(filepath)
        suffix = path.suffix.lower()
        if suffix == ".pyfds":
            from pyfds.io.serializer import Serializer
            p = Serializer().load(filepath)
        elif suffix == ".fds":
            from pyfds.io.fds_parser import FdsParser
            p = FdsParser().parse(filepath)
        else:
            raise ValueError(f"Unknown format: {suffix!r}. Use .fds or .pyfds")

        chid = getattr(p, "chid", path.stem)
        self._projects[chid] = p
        self._activate(chid)
        logger.info("SessionManager: opened %r as %r", filepath, chid)
        return p

    def save_project(
        self,
        filepath: str,
        chid: Optional[str] = None,
    ) -> None:
        """
        Save the project identified by *chid* (default: active project).
        """
        p = self._resolve(chid)
        suffix = Path(filepath).suffix.lower()
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        if suffix == ".pyfds":
            from pyfds.io.serializer import Serializer
            Serializer().save(p, filepath)
        elif suffix == ".fds":
            from pyfds.io.fds_writer import FdsWriter
            FdsWriter().write(p, filepath)
        else:
            raise ValueError(f"Unknown format: {suffix!r}")
        logger.info("SessionManager: saved %r to %s", getattr(p, "chid", "?"), filepath)

    def close_project(self, chid: Optional[str] = None) -> None:
        """
        Remove a project from the session.

        If *chid* is the active project, the most recently added remaining
        project becomes active.  Raises ``KeyError`` if the session would
        become empty.
        """
        target = chid or self._active_chid
        if target not in self._projects:
            raise KeyError(f"No project {target!r} in session")
        if len(self._projects) == 1:
            raise RuntimeError("Cannot close the last open project")
        del self._projects[target]
        if self._active_chid == target:
            # Activate the last remaining project
            self._activate(list(self._projects)[-1])
        logger.info("SessionManager: closed project %r", target)

    def switch_project(self, chid: str) -> Any:
        """
        Make *chid* the active project.  Returns the project.
        """
        if chid not in self._projects:
            raise KeyError(f"No project {chid!r} in session. "
                           f"Available: {list(self._projects)}")
        self._activate(chid)
        return self._projects[chid]

    # ── Introspection ─────────────────────────────────────────────────────────

    def project_list(self) -> List[str]:
        """Return the list of open project chids."""
        return list(self._projects)

    def get_project(self, chid: str) -> Optional[Any]:
        return self._projects.get(chid)

    def __len__(self) -> int:
        return len(self._projects)

    def __repr__(self) -> str:
        return (f"<SessionManager active={self._active_chid!r} "
                f"open={list(self._projects)!r}>")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _activate(self, chid: str) -> None:
        self._active_chid = chid
        self._api._project = self._projects[chid]
        self._api._rebind_managers()
        from pyfds.core.events import get_global_bus, EventType
        get_global_bus().emit(
            EventType.PROJECT_LOADED,
            {"chid": chid},
            source="SessionManager",
        )

    def _resolve(self, chid: Optional[str]) -> Any:
        if chid is None:
            return self.active_project
        if chid not in self._projects:
            raise KeyError(f"No project {chid!r} in session")
        return self._projects[chid]
