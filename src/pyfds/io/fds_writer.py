"""
PyFDS FDS Writer  (v2.1 — Phase 1 additions)
=============================================
Serializes an ``FdsProject`` to a valid NIST FDS input file (.fds).

Phase 1 fixes and additions:
  - MULT DX0/DY0/DZ0 now serialized when non-zero.
  - ZONE LEAK_AREAS now serialized.
  - MATL multi-reaction block (N_REACTIONS / per-reaction fields).
  - REAC FUEL_RADCAL_ID / CHECK_ATOM_BALANCE.
  - DEVC QUANTITY2 / DUCT_ID.
  - INIT SHAPE / RADIUS / XYZ_CENTER.
  - MESH CYLINDRICAL flag.
  - CTRL DEADBAND / PERCENTILE_RANK / RAMP_ID.
  - DUMP PLOT3D_QUANTITY(n) array.
  - New writers: _write_geom, _write_plot3d, _write_mesh_transform.
"""
from __future__ import annotations

import re

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyfds.domain.model import FdsProject, Ramp

from .fds_writer_devices import (  # noqa: F401  (re-exported)
    FdsWriterDevicesMixin,
)
from .fds_writer_geometry import (  # noqa: F401  (re-exported)
    FdsWriterGeometryMixin,
)
from .fds_writer_head import (  # noqa: F401  (re-exported)
    FdsWriterHeadMixin,
)
from .fds_writer_hvac import (  # noqa: F401  (re-exported)
    FdsWriterHvacMixin,
)
from .fds_writer_physics import (  # noqa: F401  (re-exported)
    FdsWriterPhysicsMixin,
)
from .fds_writer_common import (  # noqa: F401  (re-exported)
    NUMBER_STYLES,
    _NUMFMT,
    _VERSION_ORDER,
    _fds_bool,
    _fmt,
    _fmt_float,
    _nl,
    _with_extra,
    check_number_format,
)



logger = logging.getLogger(__name__)


class FdsWriter(FdsWriterHeadMixin, FdsWriterPhysicsMixin, FdsWriterGeometryMixin, FdsWriterDevicesMixin, FdsWriterHvacMixin):
    """Serialize an ``FdsProject`` to a valid FDS input file."""

    @staticmethod
    def _fds_ver(project: FdsProject) -> int:
        """Return an integer version key for fast comparisons."""
        v = getattr(project, "fds_version", "latest")
        return _VERSION_ORDER.get(v, 999)

    @staticmethod
    def _requires(project: FdsProject, min_ver: str) -> bool:
        """Return True if the project's FDS version is >= *min_ver*."""
        return FdsWriter._fds_ver(project) >= _VERSION_ORDER.get(min_ver, 999)

    def to_string(self, project: FdsProject) -> str:
        """Alias for ``generate_content`` — returns the FDS input as a string."""
        return self.generate_content(project)

    def write(self, project: FdsProject, filepath: str) -> None:
        """Write *project* to *filepath*, creating parent directories as needed."""
        path = Path(filepath).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.generate_content(project)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        logger.info("FDS file written: %s", path)

    def _entity_table(self, project: FdsProject):
        """``[(tag, collection, writer_fn), ...]`` in file order."""
        return [
            ("MATL",   project.materials,       self._write_material),
            ("REAC",   project.reactions,        self._write_reaction),
            ("SPEC",   project.species,          self._write_species),
            ("SURF",   project.surfaces,         self._write_surface),
            ("MESH",   sorted(project.meshes, key=lambda m: (m.priority is None, m.priority or 0)),
                                                  self._write_mesh),
            ("TRNX",   project.mesh_transforms,  self._write_mesh_transform),
            ("OBST",   project.obstructions,     self._write_obst),
            ("HOLE",   project.holes,            self._write_hole),
            ("MULT",   project.mults,            self._write_mult),
            ("GEOM",   project.geoms,            self._write_geom),
            ("VENT",   project.vents,            self._write_vent),
            ("INIT",   project.inits,            self._write_init),
            ("PART",   project.particles,        self._write_particle),
            ("PROP",   project.props,            self._write_prop),
            ("DEVC",   project.devices,          self._write_device),
            ("CTRL",   project.controls,         self._write_control),
            ("SLCF",   project.slices,           self._write_slice),
            ("SM3D",   project.smoke3ds,         self._write_smoke3d),
            ("BNDF",   project.bndfs,            self._write_bndf),
            ("ISOF",   project.isofs,            self._write_isof),
            ("PL3D",   project.plot3ds,          self._write_plot3d),
            ("HVAC",   project.hvacs,             self._write_hvac),
            ("NODE",   project.hvac_nodes,       self._write_hvac_node),
            ("DUCT",   project.hvac_ducts,       self._write_hvac_duct),
            ("FAN",    project.fans,             self._write_fan),
            ("DAMPER", project.dampers,          self._write_damper),
            ("ZONE",    project.zones,            self._write_zone),
            ("PROF",    project.profs,            self._write_prof),
            # Gap-fill
            ("WIND",    project.wind_profiles,    self._write_wind_profile),
            ("MOVE",    project.moves,            self._write_move),
            ("FILTER",  project.hvac_filters,     self._write_hvac_filter),
            ("LEAK",    project.hvac_leakages,    self._write_hvac_leakage),
            ("AIRCOIL", project.hvac_aircoils,    self._write_hvac_aircoil),
        ]

    def generate_content(self, project: FdsProject, number_format: Optional[Dict[str, Any]] = None) -> str:
        """The whole FDS file. *number_format* (or ``project.number_format``) sets float precision/style."""
        fmt = check_number_format(number_format if number_format is not None
                                  else getattr(project, "number_format", None))
        token = _NUMFMT.set(fmt)
        try:
            return self._generate(project)
        finally:
            _NUMFMT.reset(token)

    def entity_records(self, project: FdsProject, entities, substitute=None) -> List[str]:
        """The FDS lines of just these entities (in file order) - what 'copy as FDS text' puts on the clipboard.

        *substitute* maps ``id(entity)`` to a stand-in that is written in its place (an editor previews unsaved
        edits that way without touching the project)."""
        self._project = project
        substitute = substitute or {}
        wanted = {id(e) for e in entities}
        fmt = check_number_format(getattr(project, "number_format", None))
        token = _NUMFMT.set(fmt)
        try:
            lines: List[str] = []
            for _tag, collection, writer_fn in self._entity_table(project):
                for obj in collection:
                    if id(obj) in wanted:
                        shown = substitute.get(id(obj), obj)
                        rec = writer_fn(shown)
                        if rec:
                            lines.append(_with_extra(rec, getattr(shown, "fds_extra", None)))
            for ramp in project.ramps:
                if id(ramp) in wanted:
                    lines.extend(self._ramp_lines(ramp))
            return lines
        finally:
            _NUMFMT.reset(token)

    def _ramp_lines(self, ramp: Ramp) -> List[str]:
        """One ``&RAMP`` line per T/F pair."""
        out: List[str] = []
        for i, (t, f) in enumerate(zip(ramp.times, ramp.values)):
            row: Dict[str, Any] = {"ID": ramp.name, "T": t, "F": f}
            # DEVC_ID / CTRL_ID / INTERPOLATION appear on the first row only
            if i == 0:
                if getattr(ramp, "devc_id", None):      row["DEVC_ID"]      = ramp.devc_id
                if getattr(ramp, "ctrl_id", None):      row["CTRL_ID"]      = ramp.ctrl_id
                if getattr(ramp, "interpolation", None): row["INTERPOLATION"] = ramp.interpolation
            out.append(_nl("RAMP", row))
        return out

    def _generate(self, project: FdsProject) -> str:
        self._project = project   # version-gate access in _write_* helpers
        lines: List[str] = []

        # ── HEAD ─────────────────────────────────────────────────────────────
        head: Dict[str, Any] = {"CHID": project.chid}
        if project.title:
            head["TITLE"] = project.title
        lines.append(_with_extra(_nl("HEAD", head), getattr(project, "head_extra", None)))
        lines.append("")

        # ── Global parameter blocks ───────────────────────────────────────────
        for line, block in (
            (self._write_time(project), project.params),
            (self._write_dump(project), project.dump),
            (self._write_misc(project), project.misc),
            (self._write_pres(project), project.pres),
            (self._write_radi(project), project.radi),
        ):
            line = _with_extra(line, getattr(block, "fds_extra", None))
            if not re.fullmatch(r"&\w+\s*/", line):           # nothing set and nothing kept: no record at all
                lines.append(line)
        lines.append("")

        # ── Entity groups ─────────────────────────────────────────────────────
        writers = self._entity_table(project)

        for tag, collection, writer_fn in writers:
            for obj in collection:
                if not getattr(obj, "enabled", True):
                    continue
                try:
                    rec = writer_fn(obj)
                    if rec:
                        lines.append(_with_extra(rec, getattr(obj, "fds_extra", None)))
                except Exception as exc:
                    logger.error("Writer error for &%s ID=%s: %s",
                                 tag, getattr(obj, "name", "?"), exc)

        # ── RAMP  (one line per T/F pair) ─────────────────────────────────────
        lines.append("")
        for ramp in project.ramps:
            if getattr(ramp, "enabled", True):
                lines.extend(self._ramp_lines(ramp))

        # ── Raw text blocks ───────────────────────────────────────────────────
        for txt in project.texts:
            lines.append(txt.content)

        # ── Namelists PyFDS has no model for: re-emitted verbatim ─────────────
        for raw in getattr(project, "raw_records", ()):
            lines.append(raw)

        lines.append("")
        lines.append("&TAIL /")
        return "\n".join(lines)

    def _xb(self, obj: Any) -> List[float]:
        return [obj.x_min, obj.x_max, obj.y_min, obj.y_max, obj.z_min, obj.z_max]
