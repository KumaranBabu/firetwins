"""Global parameter namelists: HEAD, TIME, DUMP, MISC, PRES, RADI.

Mixin for ``FdsParser``: each ``_parse_<tag>`` turns one tokenised record into entities.
"""
from __future__ import annotations

import logging
from typing import Dict, List
from pyfds.domain.model import FdsProject

logger = logging.getLogger(__name__)


class ParamBuilders:
    def _parse_head(self, p: FdsProject, d: Dict) -> None:
        p.chid = self._str(d, "CHID", "pyfds_case")
        p.title = self._str(d, "TITLE", "")

    def _parse_time(self, p: FdsProject, d: Dict) -> None:
        if "T_END" in d:    p.params.t_end = float(d["T_END"])
        if "T_BEGIN" in d:  p.params.t_begin = float(d["T_BEGIN"])
        if "DT" in d:       p.params.dt = float(d["DT"])

    def _parse_dump(self, p: FdsProject, d: Dict) -> None:
        for attr, key in [
            ("dt_slcf", "DT_SLCF"), ("dt_pl3d", "DT_PL3D"),
            ("dt_bndf", "DT_BNDF"), ("dt_isof", "DT_ISOF"),
            ("dt_devc", "DT_DEVC"), ("dt_ctrl",  "DT_CTRL"),
            ("dt_restart", "DT_RESTART"),
        ]:
            v = self._flt(d, key)
            if v is not None:
                setattr(p.dump, attr, v)
        p.dump.plot3d  = self._bool(d, "PLOT3D",  p.dump.plot3d)
        p.dump.smoke3d = self._bool(d, "SMOKE3D", p.dump.smoke3d)
        nframes = self._int(d, "NFRAMES")
        if nframes is not None: p.dump.nframes = nframes
        col_limit = self._int(d, "COLUMN_DUMP_LIMIT")
        if col_limit is not None: p.dump.column_dump_limit = col_limit
        # Extended DUMP fields
        dt_hrr = self._flt(d, "DT_HRR")
        if dt_hrr is not None: p.dump.dt_hrr = dt_hrr
        dt_mass = self._flt(d, "DT_MASS")
        if dt_mass is not None: p.dump.dt_mass = dt_mass
        sig_figs = self._int(d, "SIG_FIGS")
        if sig_figs is not None: p.dump.sig_figs = sig_figs
        sig_figs_exp = self._int(d, "SIG_FIGS_EXP")
        if sig_figs_exp is not None: p.dump.sig_figs_exp = sig_figs_exp
        max_part = self._int(d, "MAXIMUM_PARTICLES")
        if max_part is not None: p.dump.maximum_particles = max_part
        if self._bool(d, "VELOCITY_ERROR_FILE"): p.dump.velocity_error_file = True
        flush = self._bool(d, "FLUSH_FILE_BUFFERS", None)
        if flush is not None: p.dump.flush_file_buffers = flush
        # Phase 1: parse PLOT3D_QUANTITY(n) entries (up to 5)
        qtys: List[str] = []
        for i in range(1, 6):
            k = f"PLOT3D_QUANTITY({i})"
            if k in d:
                qtys.append(self._str(d, k))
        if qtys:
            p.dump.plot3d_quantities = qtys

    def _parse_misc(self, p: FdsProject, d: Dict) -> None:
        if "TMPA"     in d: p.misc.tmpa = float(d["TMPA"])
        if "HUMIDITY" in d: p.misc.humidity = float(d["HUMIDITY"])
        if "P_INF"    in d: p.misc.p_inf = float(d["P_INF"])
        if "U0"       in d: p.misc.u0 = float(d["U0"])
        if "V0"       in d: p.misc.v0 = float(d["V0"])
        if "W0"       in d: p.misc.w0 = float(d["W0"])
        p.misc.baroclinic      = self._bool(d, "BAROCLINIC",      p.misc.baroclinic)
        p.misc.dns             = self._bool(d, "DNS",              p.misc.dns)
        p.misc.restart         = self._bool(d, "RESTART",         p.misc.restart)
        p.misc.suppression     = self._bool(d, "SUPPRESSION",     p.misc.suppression)
        if "TURBULENCE_MODEL" in d:
            p.misc.turbulence_model = self._str(d, "TURBULENCE_MODEL")
        if "GVEC" in d:
            vals = [float(v.strip()) for v in d["GVEC"].split(",")]
            if len(vals) == 3:
                p.misc.gvec = tuple(vals)
        for axis in ("GX", "GY", "GZ"):
            rid = self._str(d, f"RAMP_{axis}")
            if rid: setattr(p.misc, f"ramp_{axis.lower()}", rid)
        omp = self._int(d, "OPENMP_THREADS")
        if omp is not None: p.misc.openmp_threads = omp
        # Extended MISC fields
        p.misc.noise = self._bool(d, "NOISE", p.misc.noise)
        noise_v = self._flt(d, "NOISE_VELOCITY")
        if noise_v is not None: p.misc.noise_velocity = noise_v
        strat = self._bool(d, "STRATIFICATION", None)
        if strat is not None: p.misc.stratification = strat
        if self._bool(d, "SOLID_PHASE_ONLY"): p.misc.solid_phase_only = True
        max_lp = self._int(d, "MAX_LEAK_PATHS")
        if max_lp is not None: p.misc.max_leak_paths = max_lp
        vn_max = self._flt(d, "VN_MAX")
        if vn_max is not None: p.misc.vn_max = vn_max
        p.misc.visibility_factor = self._flt(d, "VISIBILITY_FACTOR")
        p.misc.maximum_visibility = self._flt(d, "MAXIMUM_VISIBILITY")
        p.misc.particle_cfl = bool(self._bool(d, "PARTICLE_CFL", False))
        p.misc.particle_cfl_max = self._flt(d, "PARTICLE_CFL_MAX")

    def _parse_pres(self, p: FdsProject, d: Dict) -> None:
        if "VELOCITY_TOLERANCE"      in d: p.pres.velocity_tolerance = float(d["VELOCITY_TOLERANCE"])
        if "MAX_PRESSURE_ITERATIONS" in d: p.pres.max_pressure_iterations = int(float(d["MAX_PRESSURE_ITERATIONS"]))
        if "MACH_NUMBER_LIMIT"       in d: p.pres.mach_number_limit = float(d["MACH_NUMBER_LIMIT"])

    def _parse_radi(self, p: FdsProject, d: Dict) -> None:
        if "NUMBER_RADIATION_ANGLES" in d: p.radi.number_radiation_angles = int(float(d["NUMBER_RADIATION_ANGLES"]))
        if "RADIATION_ITERATIONS"    in d: p.radi.radiation_iterations = int(float(d["RADIATION_ITERATIONS"]))
        if "C_RAD"                   in d: p.radi.c_rad = float(d["C_RAD"])
