"""
PyFDS Project Serializer
========================
Saves and loads ``FdsProject`` objects as JSON (.pyfds archives).

The JSON format is a lossless representation of the full entity graph
(minus binary data such as slice frames). It round-trips all Pydantic
model fields through a ``model_dump`` / ``model_validate`` cycle.

Format layout::

    {
      "version":  "2.0",
      "chid":     "my_case",
      "title":    "My fire scenario",
      "params":   { ... },
      "dump":     { ... },
      "misc":     { ... },
      "pres":     { ... },
      "radi":     { ... },
      "meshes":   [ {...}, ... ],
      "surfaces": [ {...}, ... ],
      ...
    }
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Type

from pyfds.core.exceptions import FdsSerializationError
from pyfds.domain.model import (
    FdsProject, Mesh, Obstruction, Hole, Mult, Surface, Vent, Material,
    Reaction, Device, Ramp, Control, Prop, Particle, Species, Init,
    Hvac, HvacNode, HvacDuct, Fan, Damper, Slice, BoundaryFile,
    IsoSurface, Text, Zone, Prof, FdsEntity,
    Geom, Plot3D, MeshTransform,
    WindProfile, Move, HvacFilter, HvacLeakage, HvacAircoil, Smoke3D,
)

logger = logging.getLogger(__name__)

_VERSION = "2.0"

# Ordered list of (collection_attr, entity_class) for serialization
_COLLECTIONS: List[tuple] = [
    ("meshes",       Mesh),
    ("obstructions", Obstruction),
    ("holes",        Hole),
    ("mults",        Mult),
    ("surfaces",     Surface),
    ("vents",        Vent),
    ("devices",      Device),
    ("materials",    Material),
    ("reactions",    Reaction),
    ("ramps",        Ramp),
    ("slices",       Slice),
    ("smoke3ds",     Smoke3D),
    ("bndfs",        BoundaryFile),
    ("isofs",        IsoSurface),
    ("particles",    Particle),
    ("props",        Prop),
    ("controls",     Control),
    ("species",      Species),
    ("inits",        Init),
    ("hvacs",        Hvac),
    ("hvac_nodes",   HvacNode),
    ("hvac_ducts",   HvacDuct),
    ("fans",         Fan),
    ("dampers",      Damper),
    ("zones",        Zone),
    ("profs",        Prof),
    ("texts",        Text),
    # Phase 1
    ("geoms",          Geom),
    ("plot3ds",        Plot3D),
    ("mesh_transforms", MeshTransform),
    # Gap-fill
    ("wind_profiles",  WindProfile),
    ("moves",          Move),
    ("hvac_filters",   HvacFilter),
    ("hvac_leakages",  HvacLeakage),
    ("hvac_aircoils",  HvacAircoil),
]


class Serializer:
    """JSON serializer/deserializer for ``FdsProject`` objects."""

    # ── Save ─────────────────────────────────────────────────────────────────

    def save(self, project: FdsProject, filepath: str) -> None:
        """
        Serialize *project* to a .pyfds JSON file at *filepath*.

        Raises
        ------
        FdsSerializationError
            On any I/O or serialization failure.
        """
        try:
            data = self._to_dict(project)
            json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", json_bytes)
            logger.info("Project serialized to %s", path)
        except Exception as exc:
            raise FdsSerializationError(
                f"Failed to save project to {filepath}: {exc}"
            ) from exc

    def save_string(self, project: FdsProject) -> str:
        """Return the JSON serialization as a string (no file I/O)."""
        return json.dumps(self._to_dict(project), indent=2, ensure_ascii=False)

    # ── Load ─────────────────────────────────────────────────────────────────

    def load(self, filepath: str) -> FdsProject:
        """
        Deserialize a .pyfds JSON file into an ``FdsProject``.

        Raises
        ------
        FdsSerializationError
            On any I/O or deserialization failure.
        """
        try:
            path = Path(filepath)
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path, "r") as zf:
                    json_bytes = zf.read("project.json")
                data = json.loads(json_bytes.decode("utf-8"))
            else:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            return self._from_dict(data)
        except json.JSONDecodeError as exc:
            raise FdsSerializationError(
                f"Invalid JSON in {filepath}: {exc}"
            ) from exc
        except Exception as exc:
            raise FdsSerializationError(
                f"Failed to load project from {filepath}: {exc}"
            ) from exc

    def load_string(self, json_str: str) -> FdsProject:
        """Deserialize from a JSON string."""
        try:
            data = json.loads(json_str)
            return self._from_dict(data)
        except Exception as exc:
            raise FdsSerializationError(f"Deserialization failed: {exc}") from exc

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _to_dict(self, project: FdsProject) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "version": _VERSION,
            "chid":    project.chid,
            "title":   project.title,
            "params":  project.params.model_dump(),
            "dump":    project.dump.model_dump(),
            "misc":    project.misc.model_dump(),
            "pres":    project.pres.model_dump(),
            "radi":    project.radi.model_dump(),
        }
        for attr, _ in _COLLECTIONS:
            items = getattr(project, attr, [])
            data[attr] = [self._entity_to_dict(obj) for obj in items]
        editor = self._editor_to_dict(project)
        if editor:
            data["editor"] = editor
        if getattr(project, "raw_records", None):
            data["raw_records"] = list(project.raw_records)
        if getattr(project, "head_extra", None):
            data["head_extra"] = dict(project.head_extra)
        if getattr(project, "disabled_checks", None):
            data["disabled_checks"] = list(project.disabled_checks)
        if getattr(project, "number_format", None):
            data["number_format"] = dict(project.number_format)
        return data

    # ── Editor state (floors / groups / scenarios) ────────────────────────────
    #
    # Entity UIDs are regenerated on load, so editor data that refers to
    # entities is stored as a stable ``[collection, index]`` reference and
    # re-resolved to the new UIDs after the entities have been restored.

    @staticmethod
    def _ref_maps(project: FdsProject):
        by_uid: Dict[str, List[Any]] = {}
        for attr, _ in _COLLECTIONS:
            for i, obj in enumerate(getattr(project, attr, [])):
                by_uid[obj.uid] = [attr, i]
        return by_uid

    def _editor_to_dict(self, project: FdsProject) -> Dict[str, Any]:
        ed = getattr(project, "editor", None)
        if ed is None or ed.is_empty():
            return {}
        refs = self._ref_maps(project)

        def ref_fields(table: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
            out = []
            for uid, fields in table.items():
                ref = refs.get(uid)
                if ref is None:
                    logger.warning("Editor state refers to an entity outside the "
                                   "saved collections — dropped")
                    continue
                good = {}
                for k, v in fields.items():
                    try:
                        json.dumps(v)
                        good[k] = v
                    except TypeError:
                        logger.warning("Scenario value %r.%s is not JSON-serialisable "
                                       "— dropped", ref, k)
                out.append({"ref": ref, "fields": good})
            return out

        def ref_names(table: Dict[str, str], key: str) -> List[Dict[str, Any]]:
            return [{"ref": refs[uid], key: name}
                    for uid, name in table.items() if uid in refs]

        sc = ed.scenarios
        return {
            "floors": [{"name": f.name, "z_min": f.z_min, "z_max": f.z_max,
                        "description": f.description} for f in ed.floors.values()],
            "floor_assignments": ref_names(ed.floor_assignments, "floor"),
            "groups": [{"name": g.name, "description": g.description}
                       for g in ed.groups.values()],
            "group_memberships": ref_names(ed.group_memberships, "group"),
            "backgrounds": [dict(vars(b)) for b in ed.backgrounds.values()],
            "fire_items": {k: dict(v) for k, v in ed.fire_items.items()},
            "scenarios": [{
                "name": s.name, "description": s.description, "tags": list(s.tags),
                "overrides": ref_fields(s.overrides),
            } for s in sc.all()],
            "active_scenario": sc.active,
            "scenario_snapshots": ref_fields(sc._snapshots),
            "hidden": [refs[uid] for uid in sorted(ed.hidden) if uid in refs],
            "hidden_types": sorted(ed.hidden_types),
            "units": ed.units,
            "views": [v.to_dict() for v in ed.views.values()],
            "active_view": ed.active_view,
            "section_box": ed.section_box.to_dict() if ed.section_box else None,
        }

    def _editor_from_dict(self, project: FdsProject, data: Dict[str, Any]) -> None:
        from pyfds.domain.editor_state import Floor, Group
        from pyfds.domain.scenario import Scenario
        ed = project.editor

        def uid_of(ref):
            try:
                attr, idx = ref
                return getattr(project, attr)[idx].uid
            except Exception:
                return None

        for f in data.get("floors", []):
            ed.floors[f["name"]] = Floor(f["name"], f["z_min"], f["z_max"],
                                         f.get("description", ""))
        for g in data.get("groups", []):
            ed.groups[g["name"]] = Group(g["name"], g.get("description", ""))
        from pyfds.domain.editor_state import Background
        for b in data.get("backgrounds", []):
            try:
                ed.backgrounds[b["name"]] = Background(**b)
            except TypeError:
                logger.warning("Skipped an unreadable background %r", b.get("name"))
        for k, v in data.get("fire_items", {}).items():
            ed.fire_items[k] = dict(v)
        for a in data.get("floor_assignments", []):
            uid = uid_of(a["ref"])
            if uid and a["floor"] in ed.floors:
                ed.floor_assignments[uid] = a["floor"]
        for m in data.get("group_memberships", []):
            uid = uid_of(m["ref"])
            if uid and m["group"] in ed.groups:
                ed.group_memberships[uid] = m["group"]
        for sd in data.get("scenarios", []):
            sc = Scenario(name=sd["name"], description=sd.get("description", ""),
                          tags=list(sd.get("tags", [])))
            for o in sd.get("overrides", []):
                uid = uid_of(o["ref"])
                if uid:
                    sc.overrides[uid] = dict(o["fields"])
            ed.scenarios._scenarios[sc.name] = sc
        ed.scenarios._active = data.get("active_scenario")
        for o in data.get("scenario_snapshots", []):
            uid = uid_of(o["ref"])
            if uid:
                ed.scenarios._snapshots[uid] = dict(o["fields"])
        for ref in data.get("hidden", []):
            uid = uid_of(ref)
            if uid:
                ed.hidden.add(uid)
        ed.hidden_types = {str(t) for t in data.get("hidden_types", [])}
        ed.units = data.get("units", "SI") if data.get("units") in ("SI", "EN") else "SI"
        from pyfds.domain.views import SavedView, SectionBox
        for v in data.get("views", []):
            try:
                ed.views[v["name"]] = SavedView.from_dict(v)
            except (KeyError, TypeError):
                logger.warning("Skipped an unreadable saved view")
        ed.active_view = data.get("active_view") if data.get("active_view") in ed.views else None
        if data.get("section_box"):
            ed.section_box = SectionBox.from_dict(data["section_box"])

    def _entity_to_dict(self, obj: FdsEntity) -> Dict[str, Any]:
        """Dump a Pydantic model to dict, excluding private attributes."""
        return obj.model_dump(exclude_none=True)

    def _from_dict(self, data: Dict[str, Any]) -> FdsProject:
        version = data.get("version", "1.0")
        if version not in ("1.0", "2.0"):
            logger.warning("Unknown pyfds version %r — attempting to load anyway", version)

        project = FdsProject()
        project.chid  = data.get("chid",  "pyfds_case")
        project.title = data.get("title", "")

        # Sub-model params
        for attr, model_cls in [
            ("params", project.params.__class__),
            ("dump",   project.dump.__class__),
            ("misc",   project.misc.__class__),
            ("pres",   project.pres.__class__),
            ("radi",   project.radi.__class__),
        ]:
            if attr in data:
                try:
                    setattr(project, attr, model_cls(**data[attr]))
                except Exception as exc:
                    logger.warning("Could not restore %s: %s", attr, exc)

        # Entity collections
        for attr, cls in _COLLECTIONS:
            for item_dict in data.get(attr, []):
                try:
                    obj = cls(**item_dict)
                    project.add_entity(obj)
                except Exception as exc:
                    logger.warning("Could not restore %s item: %s — %s",
                                   attr, item_dict.get("name", "?"), exc)

        project.raw_records = [str(r) for r in data.get("raw_records", [])]
        project.head_extra = {str(k): str(v) for k, v in data.get("head_extra", {}).items()}
        project.disabled_checks = [str(n) for n in data.get("disabled_checks", [])]
        project.number_format = dict(data["number_format"]) if data.get("number_format") else None

        if "editor" in data:
            try:
                self._editor_from_dict(project, data["editor"])
            except Exception as exc:
                logger.warning("Could not restore editor state: %s", exc)

        logger.info("Project deserialized: chid=%r, %s", project.chid, project)
        return project
