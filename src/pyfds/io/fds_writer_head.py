"""FDS writer part: &HEAD-level records (TIME, DUMP, MISC, PRES, RADI)."""
from __future__ import annotations

from typing import Any, Dict

from pyfds.domain.model import FdsProject

from .fds_writer_common import _nl


class FdsWriterHeadMixin:
    def _write_time(self, p: FdsProject) -> str:
        d: Dict[str, Any] = {"T_END": p.params.t_end, "T_BEGIN": p.params.t_begin}
        if p.params.dt:
            d["DT"] = p.params.dt
        if not p.params.restrict_time_step:      d["RESTRICT_TIME_STEP"] = False      # FDS default is .TRUE.
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
        if p.dump.maximum_particles is not None: d["MAXIMUM_PARTICLES"] = p.dump.maximum_particles
        if p.dump.write_xyz:                     d["WRITE_XYZ"]         = True
        if p.dump.render_file:                   d["RENDER_FILE"]       = p.dump.render_file
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
        initial_wind = {k.upper(): getattr(p.misc, k) for k in ("u0", "v0", "w0") if getattr(p.misc, k) != 0.0}
        if initial_wind and not self._requires(p, "6.9"):
            d.update(initial_wind)                                  # older FDS keeps the initial wind in &MISC
        # OPENMP_THREADS is not an FDS keyword (real FDS stops with ERROR 101): threads come from the OMP_NUM_THREADS environment variable
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
        if p.misc.visibility_factor is not None:  d["VISIBILITY_FACTOR"]  = p.misc.visibility_factor
        if p.misc.maximum_visibility is not None: d["MAXIMUM_VISIBILITY"] = p.misc.maximum_visibility
        if p.misc.no_pressure_zones:              d["NO_PRESSURE_ZONES"]  = True
        if p.misc.minimum_zone_volume is not None: d["MINIMUM_ZONE_VOLUME"] = p.misc.minimum_zone_volume
        if p.misc.particle_cfl:                   d["PARTICLE_CFL"]       = True
        if p.misc.particle_cfl_max is not None:   d["PARTICLE_CFL_MAX"]   = p.misc.particle_cfl_max
        text = _nl("MISC", d)
        if initial_wind and self._requires(p, "6.9"):               # FDS 6.10 takes it from &WIND (real FDS rejects U0 in &MISC)
            text += "\n" + _nl("WIND", initial_wind)
        return text

    def _write_pres(self, p: FdsProject) -> str:
        return _nl("PRES", {
            "VELOCITY_TOLERANCE":      p.pres.velocity_tolerance,
            "MAX_PRESSURE_ITERATIONS": p.pres.max_pressure_iterations,
        })

    def _write_radi(self, p: FdsProject) -> str:
        return _nl("RADI", {
            "NUMBER_RADIATION_ANGLES": p.radi.number_radiation_angles,
            "RADIATION_ITERATIONS":    p.radi.radiation_iterations,
            **({"TIME_STEP_INCREMENT": p.radi.time_step_increment} if p.radi.time_step_increment != 3 else {}),     # FDS default is 3
        })
