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

import contextvars
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyfds.io.namelist import tokenize

from pyfds.domain.model import (
    FdsProject, Mesh, Obstruction, Hole, Mult, Surface, Vent, Material,
    Reaction, Device, Ramp, Control, Prop, Particle, Species, Init,
    Hvac, HvacNode, HvacDuct, Fan, Damper, Slice, BoundaryFile,
    IsoSurface, Text, Zone, Prof, FdsEntity,
    Geom, Plot3D, MeshTransform,
    WindProfile, Move, HvacFilter, HvacLeakage, HvacAircoil, Smoke3D,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fds_bool(v: bool) -> str:
    return ".TRUE." if v else ".FALSE."


def _fmt(v: Any) -> str:
    """Format any Python value as a Fortran namelist token."""
    if isinstance(v, bool):
        return _fds_bool(v)
    if isinstance(v, (list, tuple)):
        parts = []
        for item in v:
            if isinstance(item, bool):
                parts.append(_fds_bool(item))
            elif isinstance(item, str):
                parts.append(f"'{item}'" if not item.startswith("'") else item)
            elif isinstance(item, float):
                parts.append(_fmt_float(item))
            else:
                parts.append(str(item))
        return ",".join(parts)
    if isinstance(v, str):
        return f"'{v}'" if not (v.startswith("'") or v.startswith(".")) else v
    if isinstance(v, float):
        return _fmt_float(v)
    return str(v)


_NUMFMT: "contextvars.ContextVar" = contextvars.ContextVar("pyfds_numfmt", default=None)

NUMBER_STYLES = ("auto", "decimal", "scientific")


def check_number_format(fmt: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Validate ``{"significant_digits": 1..15 or None, "style": auto|decimal|scientific}``."""
    if fmt is None:
        return None
    unknown = set(fmt) - {"significant_digits", "style"}
    if unknown:
        raise ValueError(f"unknown number-format keys: {sorted(unknown)}")
    n, style = fmt.get("significant_digits"), fmt.get("style", "auto")
    if n is not None and (not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 15):
        raise ValueError("significant_digits must be a whole number from 1 to 15")
    if style not in NUMBER_STYLES:
        raise ValueError(f"style must be one of {', '.join(NUMBER_STYLES)}")
    return {"significant_digits": n, "style": style}


def _fmt_float(v: float) -> str:
    """Produce decimal notation FDS can reliably parse (no scientific notation gotchas)."""
    fmt = _NUMFMT.get()
    if fmt is not None and v != 0.0:
        n, style = fmt["significant_digits"], fmt["style"]
        if style == "scientific":
            return f"{v:.{(n or 6) - 1}E}".replace("E+0", "E+").replace("E-0", "E-")
        if n is not None:
            if style == "decimal" or 0.0001 <= abs(v) <= 999999.0:
                text = f"{v:.{n}g}"
                if "e" in text or "E" in text:          # %g switched to exponent: write it out in full
                    from decimal import Decimal
                    text = format(Decimal(text), "f")
                return text if "." in text else text + ".0"
            return f"{v:.{n - 1}E}".replace("E+0", "E+").replace("E-0", "E-")
    if v == 0.0:
        return "0.0"
    abs_v = abs(v)
    if 0.0001 <= abs_v <= 999999.0:
        if abs_v >= 100:
            return f"{v:.2f}"
        if abs_v >= 1:
            result = f"{v:.5f}".rstrip("0").rstrip(".")
            return result if "." in result else result + ".0"
        result = f"{v:.7f}".rstrip("0").rstrip(".")
        return result if "." in result else result + ".0"
    # Very large / small -> explicit scientific
    return f"{v:.6E}".replace("E+0", "E+").replace("E-0", "E-")


def _nl(tag: str, parts: Dict[str, Any]) -> str:
    """Build a single FDS namelist line: &TAG K1=V1, K2=V2 /"""
    tokens = [f"{k.upper()}={_fmt(v)}" for k, v in parts.items() if v is not None]
    return f"&{tag.upper()} {', '.join(tokens)} /"


def _with_extra(line: str, extra) -> str:
    """Merge pass-through parameters (``fds_extra``) into a namelist line.

    An extra with the same key as one the writer already produced *replaces*
    it (the value read from the source file is the truth), so a key never
    appears twice.
    """
    if not extra or not line.endswith(" /"):
        return line
    rec = next(tokenize(line))
    merged = dict(rec.fields)
    merged.update(extra)
    return f"&{rec.tag} " + ", ".join(f"{k}={v}" for k, v in merged.items()) + " /"


# ---------------------------------------------------------------------------
# FdsWriter
# ---------------------------------------------------------------------------

_VERSION_ORDER = {"6.7": 67, "6.8": 68, "6.9": 69, "latest": 999}


class FdsWriter:
    """Serialize an ``FdsProject`` to a valid FDS input file."""

    # ── Version gating ────────────────────────────────────────────────────────

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

    def entity_records(self, project: FdsProject, entities) -> List[str]:
        """The FDS lines of just these entities (in file order) - what 'copy as FDS text' puts on the clipboard."""
        self._project = project
        wanted = {id(e) for e in entities}
        fmt = check_number_format(getattr(project, "number_format", None))
        token = _NUMFMT.set(fmt)
        try:
            lines: List[str] = []
            for _tag, collection, writer_fn in self._entity_table(project):
                for obj in collection:
                    if id(obj) in wanted:
                        lines.append(_with_extra(writer_fn(obj), getattr(obj, "fds_extra", None)))
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
            lines.append(_with_extra(line, getattr(block, "fds_extra", None)))
        lines.append("")

        # ── Entity groups ─────────────────────────────────────────────────────
        writers = self._entity_table(project)

        for tag, collection, writer_fn in writers:
            for obj in collection:
                if not getattr(obj, "enabled", True):
                    continue
                try:
                    lines.append(_with_extra(writer_fn(obj), getattr(obj, "fds_extra", None)))
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

    # ── Parameter block writers ───────────────────────────────────────────────

    def _write_time(self, p: FdsProject) -> str:
        d: Dict[str, Any] = {"T_END": p.params.t_end, "T_BEGIN": p.params.t_begin}
        if p.params.dt:
            d["DT"] = p.params.dt
        return _nl("TIME", d)

    def _write_dump(self, p: FdsProject) -> str:
        d: Dict[str, Any] = {
            "DT_SLCF": p.dump.dt_slcf,
            "DT_BNDF": p.dump.dt_bndf,
            "DT_ISOF": p.dump.dt_isof,
            "DT_DEVC": p.dump.dt_devc,
            "DT_PL3D": p.dump.dt_pl3d,
            "SMOKE3D": p.dump.smoke3d,
        }
        if p.dump.nframes is not None:           d["NFRAMES"]           = p.dump.nframes
        if p.dump.column_dump_limit is not None: d["COLUMN_DUMP_LIMIT"] = p.dump.column_dump_limit
        # Extended DUMP fields
        if p.dump.dt_hrr is not None:            d["DT_HRR"]            = p.dump.dt_hrr
        if p.dump.dt_mass is not None:           d["DT_MASS"]           = p.dump.dt_mass
        if p.dump.dt_restart is not None:        d["DT_RESTART"]        = p.dump.dt_restart
        if getattr(p.dump, "dt_ctrl", None) is not None: d["DT_CTRL"]   = p.dump.dt_ctrl
        if p.dump.sig_figs is not None:          d["SIG_FIGS"]          = p.dump.sig_figs
        if p.dump.sig_figs_exp is not None:      d["SIG_FIGS_EXP"]      = p.dump.sig_figs_exp
        if p.dump.velocity_error_file:           d["VELOCITY_ERROR_FILE"] = True
        if not p.dump.flush_file_buffers:        d["FLUSH_FILE_BUFFERS"]  = False
        # Write PLOT3D_QUANTITY array if custom quantities are set
        if p.dump.plot3d_quantities:
            for i, qty in enumerate(p.dump.plot3d_quantities[:5], start=1):
                if qty:
                    d[f"PLOT3D_QUANTITY({i})"] = qty
        return _nl("DUMP", d)

    def _write_misc(self, p: FdsProject) -> str:
        d: Dict[str, Any] = {
            "TMPA":             p.misc.tmpa,
            "HUMIDITY":         p.misc.humidity,
            "GVEC":             list(p.misc.gvec),
            "TURBULENCE_MODEL": p.misc.turbulence_model,
        }
        # BAROCLINIC and DNS were removed from &MISC in FDS 6.9/6.10 (real FDS 6.10.1 rejects the line), so
        # write them only for older versions; newer ones take SIMULATION_MODE='DNS'.
        if not self._requires(p, "6.9"):
            d["BAROCLINIC"] = p.misc.baroclinic
            d["DNS"] = p.misc.dns
        elif p.misc.dns:
            d["SIMULATION_MODE"] = "DNS"
        for axis in ("gx", "gy", "gz"):
            if getattr(p.misc, f"ramp_{axis}"): d[f"RAMP_{axis.upper()}"] = getattr(p.misc, f"ramp_{axis}")
        if p.misc.u0 != 0.0: d["U0"] = p.misc.u0
        if p.misc.v0 != 0.0: d["V0"] = p.misc.v0
        if p.misc.w0 != 0.0: d["W0"] = p.misc.w0
        if p.misc.openmp_threads is not None: d["OPENMP_THREADS"] = p.misc.openmp_threads
        # Extended MISC fields
        if not p.misc.noise:                      d["NOISE"]              = False   # FDS default is .TRUE.
        if p.misc.p_inf != 101325.0:              d["P_INF"]              = p.misc.p_inf
        if not p.misc.suppression:                d["SUPPRESSION"]        = False   # FDS default is .TRUE.
        if p.misc.restart:                        d["RESTART"]            = True
        if p.misc.noise_velocity is not None:     d["NOISE_VELOCITY"]     = p.misc.noise_velocity
        if not p.misc.stratification:             d["STRATIFICATION"]     = False
        if p.misc.solid_phase_only:               d["SOLID_PHASE_ONLY"]   = True
        if p.misc.max_leak_paths is not None:     d["MAX_LEAK_PATHS"]     = p.misc.max_leak_paths
        if p.misc.vn_max is not None:             d["VN_MAX"]             = p.misc.vn_max
        return _nl("MISC", d)

    def _write_pres(self, p: FdsProject) -> str:
        return _nl("PRES", {
            "VELOCITY_TOLERANCE":      p.pres.velocity_tolerance,
            "MAX_PRESSURE_ITERATIONS": p.pres.max_pressure_iterations,
        })

    def _write_radi(self, p: FdsProject) -> str:
        return _nl("RADI", {
            "NUMBER_RADIATION_ANGLES": p.radi.number_radiation_angles,
            "RADIATION_ITERATIONS":    p.radi.radiation_iterations,
        })

    # ── Entity writers ────────────────────────────────────────────────────────

    def _xb(self, obj: Any) -> List[float]:
        return [obj.x_min, obj.x_max, obj.y_min, obj.y_max, obj.z_min, obj.z_max]

    def _write_material(self, obj: Material) -> str:
        d: Dict[str, Any] = {
            "ID":           obj.name,
            "DENSITY":      obj.density,
            "CONDUCTIVITY": obj.conductivity,
            "SPECIFIC_HEAT": obj.specific_heat,
            "EMISSIVITY":   obj.emissivity,
        }
        for k in ("reference_temperature", "heat_of_reaction",
                  "heat_of_combustion", "a", "e", "n_s", "nu_residue"):
            v = getattr(obj, k, None)
            if v is not None:
                d[k.upper()] = v
        # P0 fixes — missing scalar fields
        if getattr(obj, "pyrolysis_range", None) is not None: d["PYROLYSIS_RANGE"] = obj.pyrolysis_range
        if getattr(obj, "reference_rate", None) is not None:  d["REFERENCE_RATE"]  = obj.reference_rate
        if getattr(obj, "nu_gases", None):   # liquids use the current keyword, solids keep the legacy one
            d["NU_SPEC" if obj.boiling_temperature is not None else "NU_GASES"] = obj.nu_gases
        if getattr(obj, "spec_ids", None):   d["SPEC_ID"]    = obj.spec_ids
        # Temperature-dependent property ramps
        if getattr(obj, "conductivity_ramp", None):    d["CONDUCTIVITY_RAMP"]    = obj.conductivity_ramp
        if getattr(obj, "specific_heat_ramp", None):   d["SPECIFIC_HEAT_RAMP"]   = obj.specific_heat_ramp
        # Liquid fuel properties
        if getattr(obj, "absorption_coefficient", None) is not None: d["ABSORPTION_COEFFICIENT"] = obj.absorption_coefficient
        if getattr(obj, "boiling_temperature", None) is not None:    d["BOILING_TEMPERATURE"]    = obj.boiling_temperature
        # Multi-reaction: write N_REACTIONS if > 1
        # (FDS defaults N_REACTIONS to 0, so it is required even for a single reaction)
        # but only for a material that actually reacts: FDS 6.10 refuses N_REACTIONS=1 without
        # REFERENCE_TEMPERATURE (or A and E), which is what every inert material (concrete, gypsum ...) is.
        reacts = obj.reactions or obj.a is not None or obj.e is not None or obj.reference_temperature is not None             or obj.heat_of_reaction is not None or obj.boiling_temperature is not None
        if reacts and (obj.n_reactions >= 1 or obj.reactions):
            d["N_REACTIONS"] = max(obj.n_reactions, len(obj.reactions or []))
        # Per-reaction overrides
        if obj.reactions:
            a_vals   = [r.a for r in obj.reactions if r.a is not None]
            e_vals   = [r.e for r in obj.reactions if r.e is not None]
            hor_vals = [r.heat_of_reaction for r in obj.reactions if r.heat_of_reaction is not None]
            nu_spec_vals = [r.nu_spec for r in obj.reactions if getattr(r, "nu_spec", None) is not None]
            if a_vals:       d["A"]               = a_vals
            if e_vals:       d["E"]               = e_vals
            if hor_vals:     d["HEAT_OF_REACTION"] = hor_vals
            if nu_spec_vals: d["NU_SPEC"]          = nu_spec_vals
        return _nl("MATL", d)

    def _write_reaction(self, obj: Reaction) -> str:
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.fuel:          d["FUEL"] = obj.fuel
        if obj.formula:       d["FORMULA"] = obj.formula
        d["HEAT_OF_COMBUSTION"] = obj.heat_of_combustion
        d["SOOT_YIELD"]         = obj.soot_yield
        d["CO_YIELD"]           = obj.co_yield
        d["RADIATIVE_FRACTION"] = obj.radiative_fraction
        d["EPUMO2"]             = obj.epumo2
        for k in ("c", "h", "o", "n", "cl", "a", "e", "n_t"):
            v = getattr(obj, k, None)
            if v is not None:
                d[k.upper()] = v
        # Phase 1 additions
        if obj.fuel_radcal_id:     d["FUEL_RADCAL_ID"]   = obj.fuel_radcal_id
        if obj.soot_h_fraction is not None: d["SOOT_H_FRACTION"] = obj.soot_h_fraction
        if obj.spec_id_nu:   d["SPEC_ID_NU"] = obj.spec_id_nu
        if obj.nu:           d["NU"]         = obj.nu
        if obj.spec_id_n_s:  d["SPEC_ID_N_S"] = obj.spec_id_n_s
        if obj.n_s:          d["N_S"]        = obj.n_s
        # CHECK_ATOM_BALANCE introduced in FDS 6.8
        if obj.check_atom_balance and self._requires(self._project, "6.8"):
            d["CHECK_ATOM_BALANCE"] = obj.check_atom_balance
        return _nl("REAC", d)

    def _write_species(self, obj: Species) -> str:
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.mw:      d["MW"]      = obj.mw
        if obj.formula: d["FORMULA"] = obj.formula
        # P0 fixes — mixture-fraction lump species
        if getattr(obj, "spec_id", None):            d["SPEC_ID"]         = obj.spec_id
        if getattr(obj, "volume_fraction", None):    d["VOLUME_FRACTION"] = obj.volume_fraction
        if getattr(obj, "mass_fraction", None):      d["MASS_FRACTION"]   = obj.mass_fraction
        if getattr(obj, "radcal_id", None):          d["RADCAL_ID"]       = obj.radcal_id
        # Extended SPEC fields
        if getattr(obj, "background", False):                     d["BACKGROUND"]          = True
        if getattr(obj, "mass_fraction_0", None) is not None:     d["MASS_FRACTION_0"]     = obj.mass_fraction_0
        if getattr(obj, "specific_heat", None) is not None:       d["SPECIFIC_HEAT"]       = obj.specific_heat
        if getattr(obj, "reference_enthalpy", None) is not None:  d["REFERENCE_ENTHALPY"]  = obj.reference_enthalpy
        # PRIMITIVE / LUMPED_COMPONENT_ONLY only written when non-default
        if not getattr(obj, "primitive", True):                   d["PRIMITIVE"]           = False
        if getattr(obj, "lumped_component_only", False):           d["LUMPED_COMPONENT_ONLY"] = True
        return _nl("SPEC", d)

    def _write_surface(self, obj: Surface) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "COLOR": obj.color}
        if obj.heat_release_rate is not None: d["HRRPUA"]   = obj.heat_release_rate
        if obj.tau_q is not None:             d["TAU_Q"]    = obj.tau_q
        if obj.ramp_q:                        d["RAMP_Q"]   = obj.ramp_q
        if obj.ramp_t:                        d["RAMP_T"]   = obj.ramp_t
        if obj.emissivity is not None:        d["EMISSIVITY"] = obj.emissivity
        if obj.backing:                       d["BACKING"]  = obj.backing
        if obj.vel is not None:               d["VEL"]      = obj.vel
        if obj.tmp_front is not None:         d["TMP_FRONT"] = obj.tmp_front
        if obj.texture_map:                   d["TEXTURE_MAP"] = obj.texture_map
        if obj.transparency:                  d["TRANSPARENCY"] = obj.transparency
        if obj.burn_away:                     d["BURN_AWAY"] = obj.burn_away
        if obj.matl_id:                       d["MATL_ID"]  = obj.matl_id
        if obj.part_id:                       d["PART_ID"]  = obj.part_id
        # P0 fixes — missing surface fields
        if getattr(obj, "geometry", None):              d["GEOMETRY"]        = obj.geometry
        if getattr(obj, "rgb", None):                   d["RGB"]             = list(obj.rgb)
        if getattr(obj, "volume_flow", None) is not None: d["VOLUME_FLOW"]   = obj.volume_flow
        if getattr(obj, "mass_flux", None) is not None:   d["MASS_FLUX"]     = obj.mass_flux
        if getattr(obj, "ramp_v", None):                d["RAMP_V"]          = obj.ramp_v
        if getattr(obj, "tmp_back", None) is not None:  d["TMP_BACK"]        = obj.tmp_back
        if getattr(obj, "texture_width", None) is not None: d["TEXTURE_WIDTH"]  = obj.texture_width
        if getattr(obj, "texture_height", None) is not None: d["TEXTURE_HEIGHT"] = obj.texture_height
        if getattr(obj, "heat_transfer_coefficient", None) is not None:
            d["HEAT_TRANSFER_COEFFICIENT"] = obj.heat_transfer_coefficient
        # Extended SURF fields
        if getattr(obj, "adiabatic", False):                d["ADIABATIC"]              = True
        if getattr(obj, "external_flux", None) is not None: d["EXTERNAL_FLUX"]          = obj.external_flux
        if getattr(obj, "ignition_temperature", None) is not None:
            d["AUTO_IGNITION_TEMPERATURE"] = obj.ignition_temperature
        if getattr(obj, "free_slip", False):                d["FREE_SLIP"]              = True
        if getattr(obj, "no_slip", False):                  d["NO_SLIP"]                = True
        if getattr(obj, "tau_t", None) is not None:         d["TAU_T"]                  = obj.tau_t
        if getattr(obj, "roughness", None) is not None:     d["ROUGHNESS"]              = obj.roughness
        if getattr(obj, "inner_radius", None) is not None:  d["INNER_RADIUS"]           = obj.inner_radius
        if getattr(obj, "spec_id_surf", None):              d["SPEC_ID"]                = obj.spec_id_surf
        if getattr(obj, "mass_flux_total", None) is not None: d["MASS_FLUX_TOTAL"]      = obj.mass_flux_total
        if getattr(obj, "ramp_mf", None):                   d["RAMP_MF"]               = obj.ramp_mf
        if getattr(obj, "leak_path", None):                 d["LEAK_PATH"]              = obj.leak_path
        if obj.layers:
            matl_ids = [layer.material_id for layer in obj.layers]
            thicknesses = [layer.thickness for layer in obj.layers]
            d["MATL_ID"] = matl_ids
            d["THICKNESS"] = thicknesses
        return _nl("SURF", d)

    def _write_mesh(self, obj: Mesh) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XB": self._xb(obj),
                             "IJK": list(obj.cell_count)}
        if obj.mpi_processor is not None: d["MPI_PROCESS"] = obj.mpi_processor
        if obj.color:                     d["COLOR"]       = obj.color
        if obj.cylindrical:               d["CYLINDRICAL"] = obj.cylindrical
        return _nl("MESH", d)

    def _write_obst(self, obj: Obstruction) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XB": self._xb(obj)}
        if obj.surface_ids:
            # 3 entries = (top, sides, bottom) -> SURF_IDS; 6 = one per face -> SURF_ID6
            d["SURF_ID6" if len(obj.surface_ids) == 6 else "SURF_IDS"] = obj.surface_ids
        else:
            d["SURF_ID"] = obj.surface_id
        d["COLOR"]       = obj.color
        if obj.transparency: d["TRANSPARENCY"] = obj.transparency
        if obj.thicken:      d["THICKEN"]      = obj.thicken
        if obj.allow_vent:   d["ALLOW_VENT"]   = obj.allow_vent
        if obj.ctrl_id:      d["CTRL_ID"]      = obj.ctrl_id
        if obj.devc_id:      d["DEVC_ID"]      = obj.devc_id
        if obj.mult_id:      d["MULT_ID"]      = obj.mult_id
        if obj.rgb:             d["RGB"]            = list(obj.rgb)
        if obj.texture_origin:  d["TEXTURE_ORIGIN"] = list(obj.texture_origin)
        if obj.permit_hole is not None:   d["PERMIT_HOLE"]  = obj.permit_hole
        if obj.removable is not None:     d["REMOVABLE"]    = obj.removable
        if obj.bulk_density is not None:  d["BULK_DENSITY"] = obj.bulk_density
        return _nl("OBST", d)

    def _write_hole(self, obj: Hole) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XB": self._xb(obj)}
        if obj.ctrl_id: d["CTRL_ID"] = obj.ctrl_id
        return _nl("HOLE", d)

    def _write_mult(self, obj: Mult) -> str:
        d: Dict[str, Any] = {
            "ID":      obj.name,
            "DX":      obj.dx, "DY": obj.dy, "DZ": obj.dz,
            "I_LOWER": obj.i_lower, "I_UPPER": obj.i_upper,
            "J_LOWER": obj.j_lower, "J_UPPER": obj.j_upper,
            "K_LOWER": obj.k_lower, "K_UPPER": obj.k_upper,
        }
        # DX0/DY0/DZ0 — offset of the first copy (Phase 1 fix)
        if obj.dx0 != 0.0: d["DX0"] = obj.dx0
        if obj.dy0 != 0.0: d["DY0"] = obj.dy0
        if obj.dz0 != 0.0: d["DZ0"] = obj.dz0
        return _nl("MULT", d)

    def _write_vent(self, obj: Vent) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XB": self._xb(obj),
                             "SURF_ID": obj.surface_id}
        if obj.ctrl_id: d["CTRL_ID"] = obj.ctrl_id
        if obj.color:   d["COLOR"]   = obj.color
        if obj.transparency: d["TRANSPARENCY"] = obj.transparency
        # P0 fixes
        if getattr(obj, "dynamic_pressure", None) is not None: d["DYNAMIC_PRESSURE"] = obj.dynamic_pressure
        if getattr(obj, "devc_id", None):                      d["DEVC_ID"]          = obj.devc_id
        if getattr(obj, "rgb", None):                          d["RGB"]              = list(obj.rgb)
        # Extended VENT fields
        if getattr(obj, "ior", None) is not None:              d["IOR"]              = obj.ior
        if getattr(obj, "uvw", None) is not None:              d["UVW"]              = list(obj.uvw)
        if getattr(obj, "spread_rate", None) is not None:      d["SPREAD_RATE"]      = obj.spread_rate
        if getattr(obj, "tmp_exterior", None) is not None:     d["TMP_EXTERIOR"]     = obj.tmp_exterior
        return _nl("VENT", d)

    def _write_init(self, obj: Init) -> str:
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.xyz_center is None:                # XYZ (point/shape centre) replaces XB
            d["XB"] = self._xb(obj)
        if obj.temperature is not None:   d["TEMPERATURE"]   = obj.temperature
        if obj.density is not None:       d["DENSITY"]       = obj.density
        # Multi-species takes priority over single spec_id/mass_fraction
        if getattr(obj, "spec_ids", None):
            d["SPEC_ID"]       = obj.spec_ids
            if getattr(obj, "mass_fractions", None):
                d["MASS_FRACTION"] = obj.mass_fractions
        else:
            if obj.spec_id:                   d["SPEC_ID"]       = obj.spec_id
            if obj.mass_fraction is not None: d["MASS_FRACTION"] = obj.mass_fraction
        if obj.part_id:                   d["PART_ID"]       = obj.part_id      # without it the cloud makes no particles
        if obj.n_particles is not None:   d["N_PARTICLES"]   = obj.n_particles
        # Phase 1 additions
        if obj.shape != "BLOCK":          d["SHAPE"]         = obj.shape
        if obj.radius is not None:        d["RADIUS"]        = obj.radius
        if obj.xyz_center is not None:    d["XYZ"]           = list(obj.xyz_center)
        return _nl("INIT", d)

    def _write_particle(self, obj: Particle) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "COLOR": obj.color,
                             "DIAMETER": obj.diameter,
                             "DRAG_LAW": obj.drag_law,
                             "SAMPLING_FACTOR": obj.sampling_factor}
        if not self._requires(self._project, "6.9"):          # FDS 6.10 rejects DENSITY on &PART
            d["DENSITY"] = obj.density
        if obj.prop_id: d["PROP_ID"] = obj.prop_id
        if obj.surf_id: d["SURF_ID"] = obj.surf_id
        if obj.age is not None: d["AGE"] = obj.age
        # P0 fixes — evaporation / droplet fields
        if getattr(obj, "spec_id", None):                              d["SPEC_ID"]                  = obj.spec_id
        if getattr(obj, "vaporization_temperature", None) is not None: d["VAPORIZATION_TEMPERATURE"] = obj.vaporization_temperature
        if getattr(obj, "heat_of_vaporization", None) is not None:    d["HEAT_OF_VAPORIZATION"]     = obj.heat_of_vaporization
        if getattr(obj, "n_strata", None) is not None:                 d["N_STRATA"]                 = obj.n_strata
        if getattr(obj, "gamma", None) is not None:                    d["GAMMA"]                    = obj.gamma
        if getattr(obj, "sigma", None) is not None:                    d["SIGMA"]                    = obj.sigma
        # New fields added in gap-fill
        if getattr(obj, "quantities", None):                           d["QUANTITIES"]               = obj.quantities
        if getattr(obj, "orientation", None):                          d["ORIENTATION"]              = list(obj.orientation)
        if getattr(obj, "ctrl_id", None):                              d["CTRL_ID"]                  = obj.ctrl_id
        return _nl("PART", d)

    def _write_prop(self, obj: Prop) -> str:
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.quantity:  d["QUANTITY"]  = obj.quantity
        if obj.part_id:   d["PART_ID"]   = obj.part_id
        d["RTI"]      = obj.rti
        d["C_FACTOR"] = obj.c_factor
        d["OFFSET"]   = obj.offset
        if obj.operating_pressure is not None: d["OPERATING_PRESSURE"] = obj.operating_pressure
        if obj.spray_angle: d["SPRAY_ANGLE"] = list(obj.spray_angle)
        if obj.flow_rate is not None: d["FLOW_RATE"] = obj.flow_rate
        if obj.activation_obscuration is not None: d["ACTIVATION_OBSCURATION"] = obj.activation_obscuration
        if obj.activation_temperature is not None: d["ACTIVATION_TEMPERATURE"] = obj.activation_temperature
        if obj.initial_temperature is not None:    d["INITIAL_TEMPERATURE"]    = obj.initial_temperature
        # P0 fixes — spray / smokeview fields
        if getattr(obj, "particle_velocity", None) is not None:       d["PARTICLE_VELOCITY"]       = obj.particle_velocity
        if getattr(obj, "characteristic_velocity", None) is not None: d["CHARACTERISTIC_VELOCITY"] = obj.characteristic_velocity
        if getattr(obj, "length", None) is not None:                   d["LENGTH"]                  = obj.length
        if getattr(obj, "smokeview_id", None):                         d["SMOKEVIEW_ID"]            = obj.smokeview_id
        if getattr(obj, "smokeview_parameters", None):                 d["SMOKEVIEW_PARAMETERS"]    = obj.smokeview_parameters
        return _nl("PROP", d)

    def _write_device(self, obj: Device) -> str:
        d: Dict[str, Any] = {
            "ID":       obj.name,
            "QUANTITY": obj.quantity,
            "XYZ":      [obj.x, obj.y, obj.z],
        }
        if obj.orientation:                 d["ORIENTATION"]   = list(obj.orientation)
        if obj.prop_id:                     d["PROP_ID"]       = obj.prop_id
        if obj.ctrl_id:                     d["CTRL_ID"]       = obj.ctrl_id
        if obj.setpoint is not None:        d["SETPOINT"]      = obj.setpoint
        if not obj.latch:                   d["LATCH"]         = obj.latch
        if obj.statistics:                  d["STATISTICS"]    = obj.statistics
        if obj.time_averaged:               d["TIME_AVERAGED"] = obj.time_averaged
        # Phase 1 additions
        if obj.quantity2:                   d["QUANTITY2"]     = obj.quantity2
        if obj.duct_id:                     d["DUCT_ID"]       = obj.duct_id
        # P0 fixes
        if getattr(obj, "initial_state", None) is not None:      d["INITIAL_STATE"]      = obj.initial_state
        if getattr(obj, "trip_direction", None) is not None:     d["TRIP_DIRECTION"]     = obj.trip_direction
        if getattr(obj, "spatial_statistic", None):              d["SPATIAL_STATISTIC"]  = obj.spatial_statistic
        if getattr(obj, "points", None) is not None:             d["POINTS"]             = obj.points
        if getattr(obj, "vd_to_vd", None):                       d["VD_TO_VD"]           = obj.vd_to_vd
        # Extended DEVC fields
        if getattr(obj, "xb", None) is not None:                 d["XB"]                 = list(obj.xb)
        if getattr(obj, "ior", None) is not None:                d["IOR"]                = obj.ior
        if getattr(obj, "surf_id", None):                        d["SURF_ID"]            = obj.surf_id
        if getattr(obj, "conversion_factor", None) is not None:  d["CONVERSION_FACTOR"]  = obj.conversion_factor
        if getattr(obj, "smoothed_data", False):                  d["SMOOTHED_DATA"]      = True
        if getattr(obj, "hide_coordinates", False):               d["HIDE_COORDINATES"]   = True
        if getattr(obj, "pipe_index", None) is not None:          d["PIPE_INDEX"]         = obj.pipe_index
        return _nl("DEVC", d)

    def _write_control(self, obj: Control) -> str:
        d: Dict[str, Any] = {
            "ID":            obj.name,
            "FUNCTION_TYPE": obj.function_type,
            "LATCH":         obj.latch,
            "INITIAL_STATE": obj.initial_state,
            "DELAY":         obj.delay,
        }
        if obj.input_ids and len(obj.input_ids) > 1:
            d["INPUT_ID"] = obj.input_ids      # FDS: INPUT_ID takes several ids
        elif obj.input_ids:
            d["INPUT_ID"] = obj.input_ids[0]
        elif obj.input_id:
            d["INPUT_ID"] = obj.input_id
        if obj.setpoint is not None: d["SETPOINT"]  = obj.setpoint
        if obj.on_bound:             d["ON_BOUND"]  = obj.on_bound
        if obj.n is not None:        d["N"]         = obj.n
        # Phase 1 additions
        if obj.deadband is not None:         d["DEADBAND"]       = list(obj.deadband)
        if obj.percentile_rank is not None:  d["PERCENTILE_RANK"] = obj.percentile_rank
        if obj.ramp_id:                      d["RAMP_ID"]        = obj.ramp_id
        return _nl("CTRL", d)

    def _write_slice(self, obj: Slice) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "QUANTITY": obj.quantity}
        # 3D volumetric slice uses XB; planar slice uses PBX/PBY/PBZ
        if getattr(obj, "xb", None) is not None:
            d["XB"] = list(obj.xb)
        else:
            d[f"PB{obj.plane.upper()}"] = obj.position
        if obj.vector:        d["VECTOR"]       = obj.vector
        if obj.cell_centered: d["CELL_CENTERED"] = obj.cell_centered
        if obj.quantity2:     d["QUANTITY2"]    = obj.quantity2
        return _nl("SLCF", d)

    def _write_smoke3d(self, obj: Smoke3D) -> str:
        return _nl("SM3D", {"QUANTITY": obj.quantity, "SPEC_ID": obj.spec_id})

    def _write_bndf(self, obj: BoundaryFile) -> str:
        d: Dict[str, Any] = {"QUANTITY": obj.quantity}
        if obj.cell_centered: d["CELL_CENTERED"] = obj.cell_centered
        return _nl("BNDF", d)

    def _write_isof(self, obj: IsoSurface) -> str:
        # &ISOF has no ID (FDS 6.10 rejects it) and takes VALUE(1), VALUE(2) ...; the name is editor-side only
        d: Dict[str, Any] = {"QUANTITY": obj.quantity, "VALUE(1)": obj.value}
        if obj.quantity2:          d["QUANTITY2"] = obj.quantity2
        return _nl("ISOF", d)

    def _write_hvac(self, obj: Hvac) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "DIAMETER": obj.diameter, "LENGTH": obj.length}
        if obj.vent_ids:
            d["VENT_ID"] = obj.vent_ids[0]
        if len(obj.vent_ids) > 1:
            d["VENT_ID2"] = obj.vent_ids[1]
        return _nl("HVAC", d)

    def _write_hvac_node(self, obj: HvacNode) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XYZ": [obj.x, obj.y, obj.z]}
        if obj.vent_id:   d["VENT_ID"] = obj.vent_id
        if obj.ambient:   d["AMBIENT"] = obj.ambient
        # P0 fixes
        if getattr(obj, "duct_id", None):   d["DUCT_ID"]   = obj.duct_id
        if getattr(obj, "filter_id", None): d["FILTER_ID"] = obj.filter_id
        return _nl("NODE", d)

    def _write_hvac_duct(self, obj: HvacDuct) -> str:
        d: Dict[str, Any] = {"ID": obj.name,
                             "NODE_ID": [obj.node_id_1, obj.node_id_2],
                             "DIAMETER": obj.diameter,
                             "ROUGHNESS": obj.roughness}
        if obj.length is not None: d["LENGTH"] = obj.length
        if obj.ctrl_id: d["CTRL_ID"] = obj.ctrl_id
        # P0 fixes
        if getattr(obj, "area", None) is not None:       d["AREA"]       = obj.area
        if getattr(obj, "loss", None) is not None:       d["LOSS"]       = list(obj.loss) if isinstance(obj.loss, (list, tuple)) else obj.loss
        if getattr(obj, "perimeter", None) is not None:  d["PERIMETER"]  = obj.perimeter
        if getattr(obj, "leakage_id", None):             d["LEAKAGE_ID"] = obj.leakage_id
        return _nl("DUCT", d)

    def _write_fan(self, obj: Fan) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "DUCT_ID": obj.duct_id}
        if obj.ramp_id:               d["RAMP_ID"]           = obj.ramp_id
        if obj.volume_flow_rate is not None: d["VOLUME_FLOW_RATE"] = obj.volume_flow_rate
        if obj.ctrl_id:               d["CTRL_ID"]           = obj.ctrl_id
        # P0 fixes — fan curve fields
        if getattr(obj, "max_flow", None) is not None:     d["MAX_FLOW"]     = obj.max_flow
        if getattr(obj, "max_pressure", None) is not None: d["MAX_PRESSURE"] = obj.max_pressure
        if getattr(obj, "volume_flow", None):              d["VOLUME_FLOW"]  = obj.volume_flow
        if getattr(obj, "pressure", None):                 d["PRESSURE"]     = obj.pressure
        return _nl("FAN", d)

    def _write_damper(self, obj: Damper) -> str:
        return _nl("DAMPER", {"ID": obj.name, "DUCT_ID": obj.duct_id,
                               "CTRL_ID": obj.ctrl_id})

    def _write_zone(self, obj: Zone) -> str:
        d: Dict[str, Any] = {"ID": obj.name}
        # FDS &ZONE requires a single interior XYZ point, not XB bounds.
        # Use xyz when set; fall back to centroid of the stored bounding box.
        if getattr(obj, "xyz", None) is not None:
            d["XYZ"] = list(obj.xyz)
        else:
            cx = (obj.x_min + obj.x_max) / 2.0
            cy = (obj.y_min + obj.y_max) / 2.0
            cz = (obj.z_min + obj.z_max) / 2.0
            d["XYZ"] = [cx, cy, cz]
        if obj.leak_areas:
            d["LEAK_AREAS"] = obj.leak_areas
        return _nl("ZONE", d)

    def _write_prof(self, obj: Prof) -> str:
        return _nl("PROF", {"ID": obj.name, "QUANTITY": obj.quantity,
                             "XYZ": [obj.x, obj.y, obj.z],
                             "DIRECTION": obj.direction})

    # ── Phase 1 new writers ───────────────────────────────────────────────────

    def _write_geom(self, obj: Geom) -> str:
        """Write &GEOM namelist. Vertex/face arrays are written inline."""
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.surf_ids:                    d["SURF_ID"]     = obj.surf_ids
        else:                               d["SURF_ID"]     = obj.surf_id
        if obj.is_terrain:                  d["IS_TERRAIN"]  = obj.is_terrain
        if obj.binary_file:                 d["BINARY_FILE"] = obj.binary_file
        if obj.read_binary:                 d["READ_BINARY"] = obj.read_binary
        if obj.move_id:                     d["MOVE_ID"]     = obj.move_id
        if obj.component_only:              d["COMPONENT_ONLY"] = obj.component_only
        # Inline vertex and face arrays
        if obj.verts:
            # Flatten: VERTS=x1,y1,z1,x2,y2,z2,...
            flat = [c for v in obj.verts for c in v]
            d["VERTS"] = flat
        if obj.faces:
            # Flatten: FACES=n1,n2,n3,...
            flat_f = [i for f in obj.faces for i in f]
            d["FACES"] = flat_f
        return _nl("GEOM", d)

    def _write_plot3d(self, obj: Plot3D) -> str:
        """Write &PL3D namelist."""
        d: Dict[str, Any] = {"ID": obj.name, "QUANTITY": obj.quantity}
        if obj.velo_index is not None: d["VELO_INDEX"] = obj.velo_index
        if obj.spec_id:                d["SPEC_ID"]    = obj.spec_id
        return _nl("PL3D", d)

    def _write_mesh_transform(self, obj: MeshTransform) -> str:
        """Write &TRNX/TRNY/TRNZ namelist."""
        tag = f"TRN{obj.direction.upper()}"
        d: Dict[str, Any] = {
            "MESH_NUMBER": obj.mesh_number,
            "IDERIV":      obj.ideriv,
            "CC":          obj.cc,
            "PC":          obj.pc,
        }
        return _nl(tag, d)

    # ── Gap-fill new writers ──────────────────────────────────────────────────

    def _write_wind_profile(self, obj: WindProfile) -> str:
        """Write &WIND namelist — atmospheric boundary layer profile."""
        d: Dict[str, Any] = {
            "SPEED":     obj.speed,
            "DIRECTION": obj.direction,
            "Z_REF":     obj.z_ref,
        }
        if obj.z0 is not None:       d["Z0"]       = obj.z0
        if obj.l is not None:        d["L"]        = obj.l
        if obj.ustar is not None:    d["USTAR"]    = obj.ustar
        if obj.ramp_id:              d["RAMP_ID"]  = obj.ramp_id
        if obj.latitude is not None: d["LATITUDE"] = obj.latitude
        if obj.l_inf is not None:    d["L_INF"]    = obj.l_inf
        return _nl("WIND", d)

    def _write_move(self, obj: Move) -> str:
        """Write &MOVE namelist — rigid body motion."""
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.x0 != 0.0 or obj.y0 != 0.0 or obj.z0 != 0.0:
            d["X0"] = obj.x0; d["Y0"] = obj.y0; d["Z0"] = obj.z0
        ax = list(obj.axis)
        if ax != [0.0, 0.0, 1.0]: d["AXIS"] = ax
        if obj.omega != 0.0:  d["OMEGA"]    = obj.omega
        vel = list(obj.velocity)
        if vel != [0.0, 0.0, 0.0]: d["VELOCITY"] = vel
        if obj.rotation_angle is not None: d["ROTATION_ANGLE"] = obj.rotation_angle
        if obj.dx != 0.0: d["DX"] = obj.dx
        if obj.dy != 0.0: d["DY"] = obj.dy
        if obj.dz != 0.0: d["DZ"] = obj.dz
        if obj.scale != 1.0: d["SCALE"] = obj.scale
        return _nl("MOVE", d)

    def _write_hvac_filter(self, obj: HvacFilter) -> str:
        """Write &FILTER namelist — HVAC particulate filter."""
        d: Dict[str, Any] = {"ID": obj.name, "DUCT_ID": obj.duct_id,
                             "EFFICIENCY": obj.efficiency, "LOSS": obj.loss}
        if obj.clean_loss is not None: d["CLEAN_LOSS"] = obj.clean_loss
        if obj.ctrl_id:                d["CTRL_ID"]    = obj.ctrl_id
        return _nl("FILTER", d)

    def _write_hvac_aircoil(self, obj: HvacAircoil) -> str:
        """Write &AIRCOIL namelist — duct heat exchanger."""
        d: Dict[str, Any] = {"ID": obj.name, "DUCT_ID": obj.duct_id, "EFFECTIVENESS": obj.effectiveness}
        if obj.coolant_temperature is not None:   d["COOLANT_TEMPERATURE"]   = obj.coolant_temperature
        if obj.coolant_specific_heat is not None: d["COOLANT_SPECIFIC_HEAT"] = obj.coolant_specific_heat
        if obj.coolant_mass_flow is not None:     d["COOLANT_MASS_FLOW"]     = obj.coolant_mass_flow
        if obj.ctrl_id:                           d["CTRL_ID"]               = obj.ctrl_id
        return _nl("AIRCOIL", d)

    def _write_hvac_leakage(self, obj: HvacLeakage) -> str:
        """Write &LEAK namelist — duct leakage between pressure zones."""
        d: Dict[str, Any] = {"ID": obj.name,
                             "ZONE_ID(1)": obj.zone_id_1,
                             "ZONE_ID(2)": obj.zone_id_2,
                             "AREA": obj.area}
        if obj.crack_id: d["CRACK_ID"] = obj.crack_id
        if obj.ctrl_id:  d["CTRL_ID"]  = obj.ctrl_id
        return _nl("LEAK", d)
