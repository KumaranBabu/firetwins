"""``FdsProject`` — the root container of one FDS case."""
from __future__ import annotations

from .base import FdsEntity, Observer, _MISSING
from .devices import BoundaryFile, Control, Device, IsoSurface, Plot3D, Prof, Prop, Slice, Smoke3D, Text
from .environment import Init, WindProfile
from .hvac import Damper, Fan, Hvac, HvacDuct, HvacAircoil, HvacFilter, HvacLeakage, HvacNode
from .params import DumpParams, MiscParams, PresParams, RadiParams, SimulationParams
from .physics import Material, Particle, Ramp, Reaction, Species, Surface
from .spatial import Geom, Hole, Mesh, MeshTransform, Move, Mult, Obstruction, Vent, Zone

import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class FdsProject(Observer):
    """
    The root container for all FDS model data.

    All entity collections are plain Python lists; use ``add_entity`` /
    ``remove_entity_by_uid`` to modify them so the observer chain fires.
    """

    #: FDS version string this project targets (e.g. "6.7", "6.8", "6.9").
    #: Controls which optional fields the writer emits.
    #: None means "emit everything" (newest FDS).
    FDS_VERSIONS = ("6.7", "6.8", "6.9", "latest")

    def __init__(self, chid: str = "pyfds_case", title: str = "",
                 fds_version: str = "latest") -> None:
        self._project_id: str = str(uuid.uuid4())

        # Simulation-level parameters
        self.chid: str = chid
        self.title: str = title
        self.fds_version: str = fds_version
        self.params = SimulationParams()
        self.misc = MiscParams()
        self.pres = PresParams()
        self.radi = RadiParams()
        self.dump = DumpParams()

        # Entity collections — one list per FDS namelist family
        self.meshes: List[Mesh] = []
        self.obstructions: List[Obstruction] = []
        self.holes: List[Hole] = []
        self.mults: List[Mult] = []
        self.surfaces: List[Surface] = []
        self.vents: List[Vent] = []
        self.devices: List[Device] = []
        self.materials: List[Material] = []
        self.reactions: List[Reaction] = []
        self.ramps: List[Ramp] = []
        self.slices: List[Slice] = []
        self.smoke3ds: List[Smoke3D] = []
        self.particles: List[Particle] = []
        self.props: List[Prop] = []
        self.controls: List[Control] = []
        self.inits: List[Init] = []
        self.hvacs: List[Hvac] = []
        self.hvac_nodes: List[HvacNode] = []
        self.hvac_ducts: List[HvacDuct] = []
        self.fans: List[Fan] = []
        self.dampers: List[Damper] = []
        self.bndfs: List[BoundaryFile] = []
        self.isofs: List[IsoSurface] = []
        self.species: List[Species] = []
        self.texts: List[Text] = []
        self.zones: List[Zone] = []
        self.profs: List[Prof] = []
        # Phase 1 additions
        self.geoms: List[Geom] = []
        self.plot3ds: List[Plot3D] = []
        self.mesh_transforms: List[MeshTransform] = []
        # Gap-fill additions (WIND / MOVE / FILTER / LEAK)
        self.wind_profiles: List[WindProfile] = []
        self.moves: List[Move] = []
        self.hvac_filters: List[HvacFilter] = []
        self.hvac_leakages: List[HvacLeakage] = []
        self.hvac_aircoils: List[HvacAircoil] = []

        #: Verbatim text of namelist records PyFDS has no model for (e.g. &COMB,
        #: &CLIP). Re-emitted unchanged by the writer so imports never lose them.
        self.raw_records: List[str] = []
        #: Unmodelled &HEAD parameters (same convention as ``fds_extra``).
        self.head_extra: Dict[str, str] = {}
        #: names of model checks (validation rules) switched off for this project
        self.disabled_checks: List[str] = []
        #: how floats are written to FDS: {"significant_digits": int|None, "style": auto|decimal|scientific}
        self.number_format: Optional[Dict[str, Any]] = None

        # Editor-side data (floors, groups, scenarios) — not part of the FDS file
        from ..editor_state import EditorState
        self.editor = EditorState()

        # Infrastructure
        self._global_observers: List[Observer] = []
        self._uid_index: Dict[str, FdsEntity] = {}

    # ── Collection registry ──────────────────────────────────────────────────

    _TYPE_MAP: Dict[type, str] = {
        Mesh: "meshes", Obstruction: "obstructions", Hole: "holes",
        Mult: "mults", Surface: "surfaces", Vent: "vents",
        Device: "devices", Material: "materials", Reaction: "reactions",
        Ramp: "ramps", Slice: "slices", Smoke3D: "smoke3ds", Particle: "particles",
        Prop: "props", Control: "controls", Init: "inits",
        Hvac: "hvacs", HvacNode: "hvac_nodes", HvacDuct: "hvac_ducts",
        Fan: "fans", Damper: "dampers", BoundaryFile: "bndfs",
        IsoSurface: "isofs", Species: "species", Text: "texts",
        Zone: "zones", Prof: "profs",
        # Phase 1
        Geom: "geoms", Plot3D: "plot3ds", MeshTransform: "mesh_transforms",
        # Gap-fill
        WindProfile: "wind_profiles", Move: "moves",
        HvacFilter: "hvac_filters", HvacLeakage: "hvac_leakages", HvacAircoil: "hvac_aircoils",
    }

    def _get_collection(self, cls: type) -> Optional[List]:
        """Return the collection list for *cls* (BUG-08 fix: accepts class, not instance)."""
        attr = self._TYPE_MAP.get(cls)
        if attr is None:
            # Fall back to name-based match — handles cross-module class identity
            name = cls.__name__
            for mapped_cls, mapped_attr in self._TYPE_MAP.items():
                if mapped_cls.__name__ == name:
                    attr = mapped_attr
                    break
        return getattr(self, attr, None) if attr else None

    # ── Entity CRUD ──────────────────────────────────────────────────────────

    def add(self, collection: List, obj: FdsEntity) -> None:
        """Append *obj* to *collection* and register in the UID index."""
        uid = getattr(obj, "uid", None) or getattr(obj, "id", None) or str(id(obj))
        try:
            obj.add_observer(self)
        except AttributeError:
            pass
        collection.append(obj)
        self._uid_index[uid] = obj
        self.notify_global("OBJECT_ADDED", obj)

    def add_entity(self, obj: FdsEntity) -> None:
        """Add *obj* to its natural collection (auto-detected by type)."""
        collection = self._get_collection(type(obj))
        if collection is not None:
            self.add(collection, obj)
        else:
            logger.warning("FdsProject.add_entity: unknown type %s", type(obj).__name__)

    def remove(self, collection: List, uid: str) -> None:
        """Remove entity with *uid* from *collection*."""
        obj = self._uid_index.pop(uid, None)
        if obj and obj in collection:
            collection.remove(obj)
            self.notify_global("OBJECT_REMOVED", obj)

    def remove_entity_by_uid(self, uid: str) -> None:
        """Remove an entity by UID regardless of which collection it lives in."""
        obj = self._uid_index.pop(uid, None)
        if obj is None:
            return
        for lst in self._TYPE_MAP.values():
            collection: List = getattr(self, lst, [])
            if obj in collection:
                collection.remove(obj)
                self.notify_global("OBJECT_REMOVED", obj)
                return

    def get_by_uid(self, uid: str) -> Optional[FdsEntity]:
        return self._uid_index.get(uid)

    def get_by_name(self, name: str, cls: type) -> Optional[FdsEntity]:
        """Find an entity by its ``name`` field within the collection for *cls*."""
        collection = self._get_collection(cls)
        if collection is None:
            return None
        for obj in collection:
            if getattr(obj, "name", None) == name:
                return obj
        return None

    # ── Observer wiring ──────────────────────────────────────────────────────

    def register_global_observer(self, observer: Observer) -> None:
        if observer not in self._global_observers:
            self._global_observers.append(observer)

    def update(self, event_type: str, payload: Any) -> None:
        """Receive entity-level events and re-broadcast globally."""
        self.notify_global(event_type, payload)

    def notify_global(self, event_type: str, data: Any) -> None:
        for obs in list(self._global_observers):
            obs.update(event_type, data)
        try:
            from pyfds.core.events import get_global_bus, EventType
            etype = getattr(EventType, event_type, None)
            if etype is not None:
                get_global_bus().emit(etype, data, source="FdsProject")
        except Exception:
            pass

    # ── Convenience queries ───────────────────────────────────────────────────

    @property
    def all_entities(self) -> List[FdsEntity]:
        result = []
        for attr in self._TYPE_MAP.values():
            result.extend(getattr(self, attr, []))
        return result

    def surface_ids(self) -> set:
        return {s.name for s in self.surfaces} | {"OPEN", "INERT", "MIRROR"}

    def material_ids(self) -> set:
        return {m.name for m in self.materials}

    def entity_count(self) -> Dict[str, int]:
        return {attr: len(getattr(self, attr, [])) for attr in self._TYPE_MAP.values()}

    # ── Query API ─────────────────────────────────────────────────────────────

    def find(self, cls: Type[FdsEntity]) -> List[FdsEntity]:
        """Return all entities of type *cls* (shorthand for ``filter(cls)``)."""
        col = self._get_collection(cls)
        return list(col) if col is not None else []

    def filter(self, cls: Type[FdsEntity], **kwargs: Any) -> List[FdsEntity]:
        """Return entities of *cls* whose fields all match the given keyword values."""
        collection = self._get_collection(cls)
        if collection is None:
            return []
        return [
            obj for obj in collection
            if all(getattr(obj, k, _MISSING) == v for k, v in kwargs.items())
        ]

    def query(
        self,
        cls: Type[FdsEntity],
        predicate: Callable[[FdsEntity], bool],
    ) -> List[FdsEntity]:
        """Return entities of *cls* for which *predicate(entity)* is True."""
        collection = self._get_collection(cls)
        if collection is None:
            return []
        return [obj for obj in collection if predicate(obj)]

    def find_references(self, name: str) -> List[FdsEntity]:
        """Return all entities that reference *name* in any string or list-of-string field."""
        return [e for e in self.all_entities if self._references_name(e, name)]

    @staticmethod
    def _references_name(entity: "FdsEntity", name: str) -> bool:
        for value in entity.model_dump().values():
            if isinstance(value, str) and value == name:
                return True
            if isinstance(value, list) and any(
                v == name for v in value if isinstance(v, str)
            ):
                return True
        return False

    def clear(self) -> None:
        """Remove all entities from every collection."""
        for attr in self._TYPE_MAP.values():
            getattr(self, attr, []).clear()
        self._uid_index.clear()

    def __repr__(self) -> str:
        counts = ", ".join(
            f"{k}={v}" for k, v in self.entity_count().items() if v > 0
        )
        return f"<FdsProject chid={self.chid!r} [{counts}]>"
