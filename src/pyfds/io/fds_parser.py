"""
PyFDS FDS Parser  (v2.1 — Phase 1 additions)
=============================================
Parses NIST FDS input files (.fds) into an ``FdsProject`` object.

Phase 1 additions:
  - MULT: parses DX0/DY0/DZ0.
  - ZONE: parses LEAK_AREAS.
  - MATL: parses N_REACTIONS and per-reaction arrays.
  - REAC: parses FUEL_RADCAL_ID / CHECK_ATOM_BALANCE.
  - DEVC: parses QUANTITY2 / DUCT_ID.
  - INIT: parses SHAPE / RADIUS / XYZ_CENTER.
  - MESH: parses CYLINDRICAL flag.
  - CTRL: parses DEADBAND / PERCENTILE_RANK / RAMP_ID.
  - DUMP: parses PLOT3D_QUANTITY(n) array entries.
  - New: _parse_geom (GEOM namelist).
  - New: _parse_pl3d (PL3D namelist).
  - New: _parse_mesh_transform (TRNX/TRNY/TRNZ namelists).
"""
from __future__ import annotations

import logging
from itertools import islice
from typing import Any, Dict, List, Optional, Tuple

from pyfds.core.exceptions import FdsParseError
from pyfds.io.namelist import alias_of, tokenize
from pyfds.domain.model import FdsProject, Ramp

from pyfds.io.fds_builders import (
    ParamBuilders, SpatialBuilders, PhysicsBuilders, DeviceBuilders, HvacBuilders,
)

logger = logging.getLogger(__name__)

class _Params(dict):
    """Namelist parameters that remember which keys a builder actually read.

    Whatever a builder never touches is carried through to the writer as
    ``fds_extra`` instead of being silently discarded.
    """

    def __init__(self, data):
        super().__init__(data)
        self.used = set()

    def get(self, key, default=None):
        self.used.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.used.add(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self.used.add(key)
        return super().__contains__(key)

    def pop(self, key, *default):
        self.used.add(key)
        return super().pop(key, *default)


#: Singleton namelists -> the project attribute that holds their parameters.
_PARAM_TARGETS = {"TIME": "params", "DUMP": "dump", "MISC": "misc",
                  "PRES": "pres", "RADI": "radi"}

#: Namelists that are recognised but intentionally not stored (the writer
#: always emits its own &TAIL). Every other tag without a builder is kept
#: verbatim in ``project.raw_records`` so a round trip never loses it.
_IGNORED_TAGS = frozenset({"TAIL"})


class FdsParser(ParamBuilders, SpatialBuilders, PhysicsBuilders, DeviceBuilders, HvacBuilders):
    """
    Parse an FDS input file into an ``FdsProject``.

    Attributes
    ----------
    warnings : List[str]
        Non-fatal issues encountered during parsing.
    """

    def __init__(self) -> None:
        self.warnings: List[str] = []

    def parse_string(self, text: str) -> FdsProject:
        """Parse FDS input from *text* string and return a populated :class:`FdsProject`."""
        self.warnings = []
        return self._parse_raw(text)

    def parse(self, filepath: str) -> FdsProject:
        """
        Read *filepath* and return a populated ``FdsProject``.

        Raises
        ------
        FdsParseError
            If the file cannot be opened or is not recognisable as FDS input.
        """
        self.warnings = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
        except OSError as exc:
            raise FdsParseError(f"Cannot open file: {exc}", filepath=filepath) from exc

        return self._parse_raw(raw)

    def _parse_raw(self, raw: str) -> FdsProject:
        project = FdsProject()

        # Accumulate RAMP lines keyed by ID before building objects
        # Value: (times, values, devc_id, ctrl_id, interpolation)
        ramp_accum: Dict[str, Tuple[List[float], List[float], Any, Any, Any]] = {}

        dispatch = {
            "HEAD":   self._parse_head,
            "TIME":   self._parse_time,
            "DUMP":   self._parse_dump,
            "MISC":   self._parse_misc,
            "PRES":   self._parse_pres,
            "RADI":   self._parse_radi,
            "MESH":   self._parse_mesh,
            "OBST":   self._parse_obst,
            "HOLE":   self._parse_hole,
            "MULT":   self._parse_mult,
            "SURF":   self._parse_surf,
            "VENT":   self._parse_vent,
            "MATL":   self._parse_matl,
            "REAC":   self._parse_reac,
            "DEVC":   self._parse_devc,
            "SLCF":   self._parse_slcf,
            "SM3D":   self._parse_sm3d,
            "BNDF":   self._parse_bndf,
            "ISOF":   self._parse_isof,
            "CTRL":   self._parse_ctrl,
            "PROP":   self._parse_prop,
            "PART":   self._parse_part,
            "SPEC":   self._parse_spec,
            "INIT":   self._parse_init,
            "HVAC":   self._parse_hvac,
            "NODE":   self._parse_node,
            "DUCT":   self._parse_duct,
            "FAN":    self._parse_fan,
            "DAMPER": self._parse_damper,
            "ZONE":   self._parse_zone,
            "PROF":   self._parse_prof,
            # Phase 1 additions
            "GEOM":   self._parse_geom,
            "PL3D":   self._parse_pl3d,
            "TRNX":   self._parse_mesh_transform,
            "TRNY":   self._parse_mesh_transform,
            "TRNZ":   self._parse_mesh_transform,
            # Gap-fill additions
            "WIND":   self._parse_wind,
            "MOVE":   self._parse_move,
            "FILTER": self._parse_hvac_filter,
            "LEAK":   self._parse_hvac_leakage,
            "AIRCOIL": self._parse_hvac_aircoil,
        }

        for rec in tokenize(raw):
            tag = rec.tag
            self.warnings.extend(rec.warnings)
            kwargs = _Params(rec.params)
            # Store the original tag so mesh_transform knows which direction
            kwargs["_TAG"] = tag
            kwargs.used.add("_TAG")
            known_before = len(project._uid_index)

            if tag == "RAMP":
                self._accumulate_ramp(kwargs, ramp_accum)
            elif tag in dispatch:
                try:
                    dispatch[tag](project, kwargs)
                except Exception as exc:
                    self.warnings.append(f"&{tag} (line {rec.line}): {exc}")
                else:
                    self._attach_extras(project, rec, kwargs, known_before)
            elif tag not in _IGNORED_TAGS:
                # No builder for this namelist: keep the text, never drop it.
                project.raw_records.append(rec.raw)

        self._finish_hvac(project)

        # Flush accumulated RAMP objects
        for ramp_id, (times, values, devc_id, ctrl_id, interpolation) in ramp_accum.items():
            try:
                project.add_entity(Ramp(
                    name=ramp_id, times=times, values=values,
                    devc_id=devc_id, ctrl_id=ctrl_id, interpolation=interpolation,
                ))
            except Exception as exc:
                self.warnings.append(f"&RAMP ID={ramp_id!r}: {exc}")

        if self.warnings:
            logger.warning("Parser finished with %d warning(s):", len(self.warnings))
            for w in self.warnings:
                logger.warning("  %s", w)

        logger.info("Parsed project → %s", project)
        return project

    # ── Pass-through of unmodelled parameters ────────────────────────────────

    @staticmethod
    def _unused_fields(rec, used) -> Dict[str, str]:
        """``{KEY: text}`` for every parameter of *rec* no builder read."""
        out: Dict[str, str] = {}
        aliased = set()                # the first KEY(n) of a family is also reachable as KEY
        for key, text in rec.fields:
            consumed = key in used
            base = alias_of(key)
            if base is not None and base not in aliased:
                aliased.add(base)
                consumed = consumed or base in used
            if not consumed:
                out[key] = text
        return out

    def _attach_extras(self, project, rec, params, known_before: int) -> None:
        extra = self._unused_fields(rec, params.used)
        if not extra:
            return
        if rec.tag == "HEAD":
            project.head_extra.update(extra)
            return
        target = None
        if rec.tag in _PARAM_TARGETS:
            target = getattr(project, _PARAM_TARGETS[rec.tag])
        elif len(project._uid_index) > known_before:
            created = len(project._uid_index) - known_before
            # newest-first slice keeps this O(created), not O(entities)
            target = list(islice(reversed(project._uid_index.values()), created))[-1]
        if target is None:
            self.warnings.append(
                f"&{rec.tag} (line {rec.line}): parameters not kept: {', '.join(extra)}")
            return
        merged = dict(target.fds_extra or {})
        merged.update(extra)
        target.fds_extra = merged

    # ── Body parser ──────────────────────────────────────────────────────────

    def _parse_body(self, body: str) -> Dict[str, str]:
        """Parse the inside of a namelist (``KEY=value ...``) into ``{KEY: value}``.

        Thin convenience wrapper over :func:`pyfds.io.namelist.tokenize`.
        """
        for rec in tokenize("&X " + body + " /"):
            return dict(rec.params)
        return {}

    # ── XB / XYZ helpers ─────────────────────────────────────────────────────

    def _parse_xb(self, xb_str: str) -> Tuple[float, ...]:
        """Parse 'x1,x2,y1,y2,z1,z2' — exactly 6 floats required (BUG-02 fix)."""
        try:
            vals = [float(v.strip()) for v in xb_str.split(",")]
        except ValueError as exc:
            raise FdsParseError(f"Non-numeric XB value: {xb_str!r}") from exc
        if len(vals) != 6:
            raise FdsParseError(f"XB must have exactly 6 values, got {len(vals)}: {xb_str!r}")
        return tuple(vals)

    def _parse_xyz(self, xyz_str: str) -> Tuple[float, float, float]:
        try:
            vals = [float(v.strip()) for v in xyz_str.split(",")]
        except ValueError as exc:
            raise FdsParseError(f"Non-numeric XYZ: {xyz_str!r}") from exc
        if len(vals) != 3:
            raise FdsParseError(f"XYZ must have 3 values, got {len(vals)}")
        return (vals[0], vals[1], vals[2])

    def _parse_ijk(self, ijk_str: str) -> Tuple[int, int, int]:
        try:
            vals = [int(v.strip()) for v in ijk_str.split(",")]
        except ValueError as exc:
            raise FdsParseError(f"Non-integer IJK: {ijk_str!r}") from exc
        if len(vals) != 3:
            raise FdsParseError("IJK must have 3 values")
        return (vals[0], vals[1], vals[2])

    def _parse_rgb(self, rgb_str: str) -> Tuple[int, int, int]:
        vals = [int(float(v.strip())) for v in rgb_str.split(",")]
        return (vals[0], vals[1], vals[2])

    def _flt(self, d: Dict, key: str, default=None) -> Optional[float]:
        if key in d:
            try:
                return float(d[key])
            except (ValueError, TypeError):
                return default
        return default

    def _int(self, d: Dict, key: str, default=None) -> Optional[int]:
        if key in d:
            try:
                return int(float(d[key]))
            except (ValueError, TypeError):
                return default
        return default

    def _bool(self, d: Dict, key: str, default=False):
        v = d.get(key, "").strip().upper()
        if v in (".TRUE.", "T", "TRUE", "1", "YES"):
            return True
        if v in (".FALSE.", "F", "FALSE", "0", "NO"):
            return False
        return default

    def _opt_bool(self, d: Dict, key: str) -> Optional[bool]:
        """Tri-state flag: ``None`` when the key is absent (so it is not written back)."""
        return self._bool(d, key, None) if key in d else None

    def _str_list(self, d: Dict, key: str) -> Optional[List[str]]:
        raw = d.get(key)
        if raw is None:
            return None
        return [v.strip().strip("'\"") for v in raw.split(",") if v.strip()]

    def _str(self, d: Dict, key: str, default: str = "") -> str:
        return d.get(key, default).strip().strip("'\"")

    def _indexed(self, d: Dict, base: str, convert):
        """Values of an array written as ``BASE='a','b'``, ``BASE(1)=.. BASE(2)=..`` or ``BASE(1:3)=..``
        as one list in index order. Returns None (and leaves every key untouched, so it is kept verbatim
        as an extra) when the indices have gaps or a value cannot be converted."""
        import re
        found = {}
        keys = []
        for k in list(dict.keys(d)):
            m = re.fullmatch(re.escape(base) + r"(?:\((\d+)(?::(\d+))?\))?", k)
            if not m:
                continue
            keys.append(k)
            start = int(m.group(1) or 1)
            for off, raw in enumerate(v.strip().strip("'\"") for v in dict.get(d, k).split(",") if v.strip()):
                found[start + off] = raw
        if not found or sorted(found) != list(range(1, len(found) + 1)):
            return None
        try:
            out = [convert(found[i]) for i in range(1, len(found) + 1)]
        except (ValueError, TypeError):
            return None
        d.used.update(keys)
        return out

    def _strs(self, d: Dict, key: str) -> Optional[List[str]]:
        """Parse a comma-separated list of (quoted) strings for array parameters."""
        raw = d.get(key)
        if raw is None:
            return None
        out = [v.strip().strip("'\"") for v in raw.split(",") if v.strip()]
        return out or None

    def _floats(self, d: Dict, key: str) -> Optional[List[float]]:
        """Parse a comma-separated list of floats for array parameters."""
        raw = d.get(key)
        if raw is None:
            return None
        try:
            return [float(v.strip()) for v in raw.split(",") if v.strip()]
        except (ValueError, TypeError):
            return None

    # ── Namelist builders ─────────────────────────────────────────────────────


    def _accumulate_ramp(self, d: Dict, accum: Dict) -> None:
        """Collect (T, F) pairs across multiple &RAMP lines (BUG-03 fix)."""
        ramp_id = self._str(d, "ID", "__unnamed__")
        t = self._flt(d, "T")
        f = self._flt(d, "F")
        if t is None or f is None:
            self.warnings.append(f"&RAMP ID={ramp_id!r}: missing T or F, skipped.")
            return
        if ramp_id not in accum:
            # First row: capture optional control fields
            devc_id = self._str(d, "DEVC_ID") or None
            ctrl_id = self._str(d, "CTRL_ID") or None
            interpolation = self._str(d, "INTERPOLATION") or None
            accum[ramp_id] = ([], [], devc_id, ctrl_id, interpolation)
        accum[ramp_id][0].append(t)
        accum[ramp_id][1].append(f)


    # ── Phase 1 new parsers ───────────────────────────────────────────────────


    # ── Gap-fill parsers ──────────────────────────────────────────────────────


