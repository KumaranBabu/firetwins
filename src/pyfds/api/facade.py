"""The FdsApi facade: wires every manager and exposes the public API.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import _CollectionManager
from .meshes import MeshManager
from .geometry import GeomManager, HoleManager, ObstManager, VentManager
from .materials import MaterialManager, ParticleManager, RampManager, ReactionManager, SurfaceManager
from .devices import ControlManager, DeviceManager
from .output import Smoke3DManager, BoundaryFileManager, IsoSurfaceManager, Plot3DManager, ProfManager, SliceManager
from .hvac import HvacManager, DamperManager, FanManager, HvacDuctManager, HvacFilterManager, HvacLeakageManager, HvacNodeManager, HvacAircoilManager
from .environment import EnvironmentManager, InitManager, WindManager
from .library import LibraryManager
from .view import VisibilityManager
from .clipboard import ClipboardManager
from .snapping import SnapManager
from .slice_view import SliceViewManager
from .scene import SceneManager
from .viewer import ViewerManager
from .fds_format import FdsFormatManager
from .checks import ValidationManager
from .run import BatchManager, ExecutionManager, HpcJobManager
from .results import ResultsManager, SmokeviewManager
from .project import HistoryManager, SessionManager, TemplateManager
from .plugins import PluginManager
from .engineering import EngineeringManager
from .config import ApiConfigProxy
from .species import SpeciesManager, ZoneManager
from .properties import PropManager, TextManager
from .transforms import MeshTransformManager, MoveManager, MultManager
from .scenarios import ScenarioManager
from .organization import Floor, FloorManager, Group, GroupManager

logger = logging.getLogger(__name__)


class FdsApi:
    """
    Primary API entry point for the pyfds backend.

    All operations on an FDS project flow through this class.

    Parameters
    ----------
    project : FdsProject, optional
        Initial project. If None, a blank project is created.
    config : FdsConfig, optional
        Runtime configuration. If None, the global config is used.

    Example::

        from pyfds.api import FdsApi

        api = FdsApi()
        api.templates.apply("room_fire", hrr=500e3)
        api.meshes.add_mesh(ijk=[20, 20, 20], xb=[0, 4, 0, 4, 0, 3])
        report = api.validation.validate()
        if report.passed:
            result = api.execution.run(output_dir="runs/room_fire")
            print(result.success, result.stats.t_reached)
    """

    def __init__(self, project=None, config=None) -> None:
        # Domain project
        if project is None:
            from pyfds.domain.model import FdsProject
            project = FdsProject()
        self._project = project

        # Configuration
        if config is None:
            from pyfds.core.config import get_config
            config = get_config()
        self._config = config

        # Managers — instantiated once, bound to this api instance
        self.history      = HistoryManager(self)
        self.meshes        = MeshManager(self)
        self.obstructions  = ObstManager(self)
        self.vents         = VentManager(self)
        self.holes         = HoleManager(self)
        self.surfaces      = SurfaceManager(self)
        self.devices       = DeviceManager(self)
        self.reactions     = ReactionManager(self)
        self.materials     = MaterialManager(self)
        self.ramps         = RampManager(self)
        self.controls      = ControlManager(self)
        self.slices        = SliceManager(self)
        self.bndfs         = BoundaryFileManager(self)
        self.smoke3ds      = Smoke3DManager(self)
        self.isofs         = IsoSurfaceManager(self)
        self.plot3ds       = Plot3DManager(self)
        self.hvac_nodes    = HvacNodeManager(self)
        self.hvac_ducts    = HvacDuctManager(self)
        self.fans          = FanManager(self)
        self.dampers       = DamperManager(self)
        self.hvac_filters  = HvacFilterManager(self)
        self.hvac_leakages = HvacLeakageManager(self)
        self.hvac_aircoils = HvacAircoilManager(self)
        self.inits         = InitManager(self)
        self.environment   = EnvironmentManager(self)
        self.library       = LibraryManager(self)
        self.view          = VisibilityManager(self)
        self.clipboard     = ClipboardManager(self)
        self.snapping      = SnapManager(self)
        self.slice_view    = SliceViewManager(self)
        self.scene         = SceneManager(self)
        self.viewer        = ViewerManager(self)
        self.fds_format    = FdsFormatManager(self)
        self.particles     = ParticleManager(self)
        self.profs         = ProfManager(self)
        self.validation    = ValidationManager(self)
        self.execution     = ExecutionManager(self)
        self.batch         = BatchManager(self)
        self.results       = ResultsManager(self)
        self.smokeview     = SmokeviewManager(self)
        self.templates     = TemplateManager(self)
        self.plugins       = PluginManager(self)
        self.meshing       = self._build_meshing_manager()
        self.session       = SessionManager(self)

        # Phase-2 feature managers
        self.geom          = GeomManager(self)
        self.hpc           = HpcJobManager(self)
        self.wind          = WindManager(self)
        self.engineering   = EngineeringManager(self)

        # Phase-4/5 feature managers
        self.scenarios     = ScenarioManager(self)
        self.floors        = FloorManager(self)
        self.groups        = GroupManager(self)

        # New Phase-1 managers
        self.selection     = self._build_selection_manager()
        self.viewport      = self._build_viewport_controller()
        self.factory       = self._build_entity_factory()

        # Entities that previously had no authoring path (G3)
        self.species          = SpeciesManager(self)
        self.zones            = ZoneManager(self)
        self.props            = PropManager(self)
        self.texts            = TextManager(self)
        self.mults            = MultManager(self)
        self.moves            = MoveManager(self)
        self.mesh_transforms  = MeshTransformManager(self)
        self.hvac             = HvacManager(self)
        self._config_proxy = ApiConfigProxy(self, config)

        logger.info("FdsApi initialised (chid=%r)", getattr(project, "chid", "?"))

    # ── Project access ────────────────────────────────────────────────────────

    @property
    def project(self):
        _session = self.__dict__.get("session")
        if _session is not None:
            return _session.active_project
        return self._project

    @property
    def config(self):
        return self._config_proxy

    @property
    def schema(self) -> Any:
        """Global SchemaRegistry (singleton) — metadata for the GUI property editor."""
        from pyfds.domain.schema import get_schema_registry
        return get_schema_registry()

    # ── I/O shortcuts ─────────────────────────────────────────────────────────

    def load(self, filepath: str) -> None:
        """
        Load a project from:
          - ``.fds``   — parse as FDS namelist input
          - ``.pyfds`` — load JSON serialised archive
        """
        _session = self.__dict__.get("session")
        if _session is not None:
            _session.open_project(filepath)
        else:
            path = Path(filepath)
            suffix = path.suffix.lower()
            if suffix == ".pyfds":
                from pyfds.io.serializer import Serializer
                self._project = Serializer().load(filepath)
            elif suffix == ".fds":
                from pyfds.io.fds_parser import FdsParser
                self._project = FdsParser().parse(filepath)
            else:
                raise ValueError(f"Unknown project format: {suffix!r}. Use .fds or .pyfds")
            self._rebind_managers()
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(EventType.PROJECT_LOADED,
                                  {"filepath": filepath}, source="FdsApi")
        logger.info("FdsApi: loaded %s", filepath)

    def save(self, filepath: str) -> None:
        """
        Save the current project:
          - ``.fds``   — write FDS namelist input
          - ``.pyfds`` — write JSON archive
        """
        path   = Path(filepath)
        suffix = path.suffix.lower()
        path.parent.mkdir(parents=True, exist_ok=True)
        if suffix == ".pyfds":
            from pyfds.io.serializer import Serializer
            Serializer().save(self._project, filepath)
        elif suffix == ".fds":
            from pyfds.io.fds_writer import FdsWriter
            FdsWriter().write(self._project, filepath)
        else:
            raise ValueError(f"Unknown format: {suffix!r}. Use .fds or .pyfds")
        from pyfds.core.events import get_global_bus, EventType
        get_global_bus().emit(EventType.PROJECT_SAVED,
                              {"filepath": filepath}, source="FdsApi")
        logger.info("FdsApi: saved %s", filepath)

    def new(self, chid: str = "pyfds_case", title: str = "") -> None:
        """Replace the current project with a blank one."""
        _session = self.__dict__.get("session")
        if _session is not None:
            _session.new_project(chid=chid, title=title)
        else:
            from pyfds.domain.model import FdsProject
            self._project = FdsProject(chid=chid, title=title)
            self._rebind_managers()
        from pyfds.core.events import get_global_bus, EventType
        get_global_bus().emit(EventType.PROJECT_CREATED, self._project, source="FdsApi")

    # ── State snapshot (GUI-ready) ─────────────────────────────────────────────

    def snapshot(self) -> Any:
        """Return an immutable state snapshot (for GUI state management)."""
        from pyfds.core.state import build_snapshot
        return build_snapshot(self._project)

    # ── Event subscription ────────────────────────────────────────────────────

    def subscribe(self, event_type, callback, **kwargs) -> int:
        """Subscribe *callback* to *event_type* on the global EventBus."""
        from pyfds.core.events import get_global_bus
        return get_global_bus().subscribe(event_type, callback, **kwargs)

    def unsubscribe(self, subscription_id: int) -> bool:
        from pyfds.core.events import get_global_bus
        return get_global_bus().unsubscribe(subscription_id)

    # ── Convenience ───────────────────────────────────────────────────────────

    def optimize_for_fire(
        self,
        surf_id: str,
        target_ratio: float = 10.0,
        fire_area: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Delegate to ``api.meshing.optimize_for_fire`` with the current project.

        Returns the D*/dx analysis dict — see :meth:`MeshingManager.optimize_for_fire`.
        """
        return self.meshing.optimize_for_fire(
            self._project,
            surf_id=surf_id,
            target_ratio=target_ratio,
            fire_area=fire_area,
        )

    def validate(self) -> List[str]:
        """Backward-compat shortcut: run validation and return a list of error message strings."""
        report = self.validation.validate()
        return [r.message for r in report.results]

    def undo(self) -> None:
        """Backward-compat shortcut: undo the last command."""
        self.history.undo()

    def plot_device(self, csv_path: str, device_name: str, output_path: str) -> None:
        """Read a device CSV and save a time-series plot to *output_path*."""
        from pyfds.results.reader import DeviceReader
        from pyfds.results.plotters import plot_device_timeseries
        import matplotlib
        matplotlib.use("Agg")
        data = DeviceReader.read(csv_path)
        fig = plot_device_timeseries(data, device_names=[device_name])
        fig.savefig(output_path, dpi=150)
        import matplotlib.pyplot as plt
        plt.close(fig)

    def set_timing(self, t_end: float, t_begin: float = 0.0) -> None:
        """Set simulation start/end time using a command (undo-able)."""
        from pyfds.automation.commands import SetTimingCommand
        self.history.execute(SetTimingCommand(self._project, t_end, t_begin))

    def set_property(self, obj: Any, attr: str, value: Any, coalesce: bool = False) -> None:
        """Set any project attribute via the undo-able command pipeline.

        ``coalesce=True`` merges consecutive edits of the same attribute into
        one undo step (use for spin boxes / drags; call ``history.seal()`` to
        end the run).
        """
        from pyfds.automation.commands import ModifyPropertyCommand
        self.history.execute(ModifyPropertyCommand(obj, attr, value), coalesce=coalesce)

    def transaction(self, label: str = "transaction", actor: Optional[str] = None):
        """``with api.transaction("Build room", actor="agent"):`` -> ONE undo step."""
        return self.history.transaction(label, actor)

    def info(self) -> str:
        """Return a human-readable summary of the current project."""
        p = self._project
        lines = [
            f"CHID    : {getattr(p, 'chid', '?')}",
            f"Title   : {getattr(p, 'title', '')}",
            f"Meshes  : {len(getattr(p, 'meshes', []))}",
            f"Obsts   : {len(getattr(p, 'obstructions', []))}",
            f"Surfs   : {len(getattr(p, 'surfaces', []))}",
            f"Devices : {len(getattr(p, 'devices', []))}",
            f"Reactions: {len(getattr(p, 'reactions', []))}",
        ]
        try:
            params = p.params
            lines.append(f"T_END   : {getattr(params, 't_end', '?')} s")
        except AttributeError:
            pass
        return "\n".join(lines)

    def __repr__(self) -> str:
        chid = getattr(self._project, "chid", "?")
        return f"<FdsApi chid={chid!r}>"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebind_managers(self) -> None:
        """Re-point all managers to the new project after load/new."""
        session = self.__dict__.get("session")
        open_projects = list(session._projects.values()) if session is not None else []
        open_projects.append(self._project)
        self.history.prune(open_projects)
        self.selection = self._build_selection_manager()

    @staticmethod
    def _build_meshing_manager():
        from pyfds.meshing.manager import MeshingManager
        from pyfds.core.events import get_global_bus
        return MeshingManager(event_bus=get_global_bus())

    def _build_selection_manager(self) -> Any:
        from pyfds.core.selection import SelectionManager
        return SelectionManager(project=self._project)

    @staticmethod
    def _build_viewport_controller() -> Any:
        from pyfds.core.viewport import ViewportController
        return ViewportController()

    @staticmethod
    def _build_entity_factory() -> Any:
        from pyfds.domain.factory import EntityFactory
        return EntityFactory()
