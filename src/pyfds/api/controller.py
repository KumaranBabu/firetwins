"""PyFDS API Controller
=====================
The ``FdsApi`` class is the single, stable façade that external callers
(CLI, scripts, future GUI, remote services) use to interact with the
entire pyfds backend.

Design principles
-----------------
* **One entry point** — callers import ``FdsApi`` and never need to reach
  into internal subpackages for standard operations.
* **Manager pattern** — each concern is delegated to a typed manager
  instance accessible as an attribute (``api.meshes``, ``api.validation``,
  etc.).
* **Session-aware** — all mutations go through the active session so
  dirty tracking and auto-save work transparently.
* **Event-driven** — every significant state change emits an event on the
  global ``EventBus`` so future GUI layers can subscribe without coupling.
* **Type-annotated** — all public methods carry complete type hints for
  IDE support and documentation generation.

Managers
--------
meshes              — MeshManager       (add/remove/query meshes)
obstructions        — ObstManager
surfaces            — SurfaceManager
devices             — DeviceManager
reactions           — ReactionManager
materials           — MaterialManager
ramps               — RampManager
controls            — ControlManager
validation          — ValidationManager (run rules, get report)
execution           — ExecutionManager  (run, cancel, queue jobs)
batch               — BatchManager      (parametric studies)
results             — ResultsManager    (index and read outputs)
smokeview           — SmokeviewManager  (launch, render, script)
templates           — TemplateManager   (apply presets)
plugins             — PluginManager     (load, list, query)
history             — HistoryManager    (undo/redo via CommandPipeline)
session             — SessionManager    (open/save/close projects)
config              — FdsConfig         (runtime configuration)

This module is a compatibility shim: the implementation now lives in the
sibling modules (``facade``, ``project``, ``run`` ...). Import from
``pyfds.api`` in new code.
"""
from __future__ import annotations

from .base import _CollectionManager  # noqa: F401
from .meshes import MeshManager  # noqa: F401
from .geometry import GeomManager, HoleManager, ObstManager, VentManager  # noqa: F401
from .materials import MaterialManager, ParticleManager, RampManager, ReactionManager, SurfaceManager  # noqa: F401
from .devices import ControlManager, DeviceManager  # noqa: F401
from .output import Smoke3DManager, BoundaryFileManager, IsoSurfaceManager, Plot3DManager, ProfManager, SliceManager  # noqa: F401
from .hvac import HvacManager, DamperManager, FanManager, HvacDuctManager, HvacFilterManager, HvacLeakageManager, HvacNodeManager  # noqa: F401
from .environment import InitManager, WindManager  # noqa: F401
from .checks import ValidationManager  # noqa: F401
from .run import BatchManager, ExecutionManager, HpcJobManager  # noqa: F401
from .results import ResultsManager, SmokeviewManager  # noqa: F401
from .project import HistoryManager, SessionManager, TemplateManager  # noqa: F401
from .plugins import PluginManager  # noqa: F401
from .engineering import EngineeringManager  # noqa: F401
from .config import ApiConfigProxy  # noqa: F401
from .species import SpeciesManager, ZoneManager  # noqa: F401
from .properties import PropManager, TextManager  # noqa: F401
from .transforms import MeshTransformManager, MoveManager, MultManager  # noqa: F401
from .scenarios import ScenarioManager  # noqa: F401
from .organization import Floor, FloorManager, Group, GroupManager  # noqa: F401
from .facade import FdsApi  # noqa: F401

__all__ = ['Smoke3DManager', 'ApiConfigProxy', 'HvacManager', 'MeshTransformManager', 'MoveManager', 'MultManager', 'PropManager', 'SpeciesManager', 'TextManager', 'ZoneManager', 'BatchManager', 'BoundaryFileManager', 'ControlManager', 'DamperManager', 'DeviceManager', 'EngineeringManager', 'ExecutionManager', 'FanManager', 'FdsApi', 'Floor', 'FloorManager', 'GeomManager', 'Group', 'GroupManager', 'HistoryManager', 'HoleManager', 'HpcJobManager', 'HvacDuctManager', 'HvacFilterManager', 'HvacLeakageManager', 'HvacNodeManager', 'InitManager', 'IsoSurfaceManager', 'MaterialManager', 'MeshManager', 'ObstManager', 'ParticleManager', 'Plot3DManager', 'PluginManager', 'ProfManager', 'RampManager', 'ReactionManager', 'ResultsManager', 'ScenarioManager', 'SessionManager', 'SliceManager', 'SmokeviewManager', 'SurfaceManager', 'TemplateManager', 'ValidationManager', 'VentManager', 'WindManager']
