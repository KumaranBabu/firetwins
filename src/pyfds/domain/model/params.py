"""Global namelist parameter blocks (&HEAD/&TIME, &DUMP, &MISC, &PRES, &RADI)."""
from __future__ import annotations


from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel


class SimulationParams(BaseModel):
    """Maps to &TIME namelist."""
    #: Parameters of this namelist that PyFDS has no typed field for, as
    #: ``{FDS_KEY: fds_value_text}`` in source order. Re-emitted verbatim by the
    #: writer so an import/export round trip never silently drops them.
    fds_extra: Optional[Dict[str, str]] = None
    t_end: float = 60.0
    t_begin: float = 0.0
    dt: Optional[float] = None
    restrict_time_step: bool = True


class DumpParams(BaseModel):
    """Maps to &DUMP namelist."""
    #: Parameters of this namelist that PyFDS has no typed field for, as
    #: ``{FDS_KEY: fds_value_text}`` in source order. Re-emitted verbatim by the
    #: writer so an import/export round trip never silently drops them.
    fds_extra: Optional[Dict[str, str]] = None
    dt_slcf: float = 1.0
    dt_pl3d: float = 10.0
    dt_bndf: float = 1.0
    dt_isof: float = 1.0
    dt_devc: float = 1.0
    dt_ctrl: float = 1.0
    dt_restart: Optional[float] = None   # FDS default is 200 s; only written when set
    plot3d: bool = True
    smoke3d: bool = True
    write_xyz: bool = False
    render_file: Optional[str] = None
    # Up to 5 Plot3D output channels (index 1..5 in FDS PLOT3D_QUANTITY array)
    plot3d_quantities: Optional[List[str]] = None
    # Output frame count (overrides DT-based output frequency)
    nframes: Optional[int] = None
    # Max columns in CSV device output (FDS default 254)
    column_dump_limit: Optional[int] = None
    # Extended DUMP fields (PyroSim parity)
    dt_hrr: Optional[float] = None        # DT_HRR — output interval for HRR file (s)
    dt_mass: Optional[float] = None       # DT_MASS — output interval for mass file (s)
    sig_figs: Optional[int] = None        # SIG_FIGS — significant figures in CSV output
    sig_figs_exp: Optional[int] = None    # SIG_FIGS_EXP — significant figures in exponential notation
    velocity_error_file: bool = False     # VELOCITY_ERROR_FILE — write velocity error diagnostics
    flush_file_buffers: bool = True       # FLUSH_FILE_BUFFERS — flush I/O after each write
    maximum_particles: Optional[int] = None  # MAXIMUM_PARTICLES - cap on Lagrangian particles (FDS default 1,000,000)


class MiscParams(BaseModel):
    """Maps to &MISC namelist."""
    #: Parameters of this namelist that PyFDS has no typed field for, as
    #: ``{FDS_KEY: fds_value_text}`` in source order. Re-emitted verbatim by the
    #: writer so an import/export round trip never silently drops them.
    fds_extra: Optional[Dict[str, str]] = None
    gvec: Tuple[float, float, float] = (0.0, 0.0, -9.81)
    #: Time ramps (RAMP ids) that scale each gravity component: RAMP_GX / RAMP_GY / RAMP_GZ
    ramp_gx: Optional[str] = None
    ramp_gy: Optional[str] = None
    ramp_gz: Optional[str] = None
    tmpa: float = 20.0
    humidity: float = 40.0
    baroclinic: bool = True
    turbulence_model: str = "DEARDORFF"
    dns: bool = False
    p_inf: float = 101325.0
    u0: float = 0.0
    v0: float = 0.0
    w0: float = 0.0
    restart: bool = False
    suppression: bool = True
    no_pressure_zones: bool = False             # NO_PRESSURE_ZONES - "Disable Pressure Zones": one background pressure everywhere
    minimum_zone_volume: Optional[float] = None  # MINIMUM_ZONE_VOLUME (m3) - voids smaller than this are filled with solid cells
    particle_cfl: bool = False                  # PARTICLE_CFL - limit the time step by the particle CFL number
    particle_cfl_max: Optional[float] = None    # PARTICLE_CFL_MAX (FDS default 1.0)
    # OpenMP threading (sets OPENMP_THREADS in &MISC and OMP_NUM_THREADS env var)
    openmp_threads: Optional[int] = None
    # Extended MISC fields (PyroSim parity)
    noise: bool = True                    # NOISE — background turbulent fluctuations (FDS default .TRUE.)
    noise_velocity: Optional[float] = None  # NOISE_VELOCITY (m/s) — amplitude of initial noise
    stratification: bool = True           # STRATIFICATION — hydrostatic pressure initialization
    solid_phase_only: bool = False        # SOLID_PHASE_ONLY — disable gas-phase solver (pyrolysis bench tests)
    max_leak_paths: Optional[int] = None  # MAX_LEAK_PATHS — maximum pressure-driven leak connections
    vn_max: Optional[float] = None        # VN_MAX — von Neumann stability limit override
    visibility_factor: Optional[float] = None   # VISIBILITY_FACTOR - C in S = C/K (3 reflecting, 8 light-emitting signs)
    maximum_visibility: Optional[float] = None  # MAXIMUM_VISIBILITY (m) reported when there is no smoke


class PresParams(BaseModel):
    """Maps to &PRES namelist."""
    #: Parameters of this namelist that PyFDS has no typed field for, as
    #: ``{FDS_KEY: fds_value_text}`` in source order. Re-emitted verbatim by the
    #: writer so an import/export round trip never silently drops them.
    fds_extra: Optional[Dict[str, str]] = None
    velocity_tolerance: float = 0.05
    max_pressure_iterations: int = 10
    mach_number_limit: float = 0.3
    pressure_iterations: int = 1
    solver: str = "SCARC"


class RadiParams(BaseModel):
    """Maps to &RADI namelist."""
    #: Parameters of this namelist that PyFDS has no typed field for, as
    #: ``{FDS_KEY: fds_value_text}`` in source order. Re-emitted verbatim by the
    #: writer so an import/export round trip never silently drops them.
    fds_extra: Optional[Dict[str, str]] = None
    number_radiation_angles: int = 104      # the FDS default (it is always written, so it must match FDS)
    radiation_iterations: int = 1
    kfst4_cutoff: float = 0.0
    c_rad: float = 1.0
    time_step_increment: int = 3
