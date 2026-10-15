"""Materials, reactions, surfaces, species, ramps and particle classes."""
from __future__ import annotations

from .base import FdsEntity


from typing import List, Optional, Tuple
from pydantic import BaseModel, Field, model_validator


class Layer(BaseModel):
    """A single material layer inside a Surface."""
    material_id: str
    thickness: float


class MaterialReaction(BaseModel):
    """A single pyrolysis reaction entry within a multi-reaction &MATL block."""
    a: Optional[float] = None                    # Arrhenius pre-exponential factor
    e: Optional[float] = None                    # Activation energy (J/mol)
    n_s: Optional[float] = None                  # Reaction order
    heat_of_reaction: Optional[float] = None     # kJ/kg
    nu_residue: Optional[float] = None           # residue mass yield (0..1)
    spec_id_residue: Optional[str] = None        # residue species ID
    heating_rate: Optional[float] = None         # reference heating rate (K/min)
    pyrolysis_range: Optional[float] = None      # peak temperature range (K)
    reference_temperature: Optional[float] = None
    nu_spec: Optional[List[float]] = None        # NU_SPEC — species yield fractions per reaction


class Material(FdsEntity):
    """&MATL namelist."""
    name: str = "DefaultMaterial"
    density: float = 1000.0
    conductivity: float = 0.5
    specific_heat: float = 1.0
    emissivity: float = 0.9
    reference_temperature: Optional[float] = None
    reference_rate: Optional[float] = None
    nu_residue: Optional[float] = None
    residue_id: Optional[str] = None                  # the material the residue is (NU_MATL needs MATL_ID)
    heat_of_reaction: Optional[float] = None
    heat_of_combustion: Optional[float] = None
    a: Optional[float] = None       # Arrhenius pre-exponential factor
    e: Optional[float] = None       # Activation energy (J/mol)
    n_s: Optional[float] = None     # Reaction order
    nu_gases: Optional[List[float]] = None
    spec_ids: Optional[List[str]] = None
    pyrolysis_range: Optional[float] = None
    heating_rate: Optional[float] = None               # HEATING_RATE (K/min) - with REFERENCE_TEMPERATURE and
                                                       # PYROLYSIS_RANGE, FDS works out A and E itself
    # Multi-reaction pyrolysis support
    n_reactions: int = 1
    reactions: List[MaterialReaction] = Field(default_factory=list)
    # Temperature-dependent property ramps
    conductivity_ramp: Optional[str] = None      # CONDUCTIVITY_RAMP — ramp ID for k(T)
    specific_heat_ramp: Optional[str] = None     # SPECIFIC_HEAT_RAMP — ramp ID for cp(T)
    # Liquid fuel properties
    absorption_coefficient: Optional[float] = None   # ABSORPTION_COEFFICIENT (1/m)
    boiling_temperature: Optional[float] = None      # BOILING_TEMPERATURE (°C)


class Reaction(FdsEntity):
    """&REAC namelist."""
    name: str = "DefaultReaction"
    fuel: Optional[str] = None
    formula: Optional[str] = None
    heat_of_combustion: float = 0.0
    soot_yield: float = 0.0
    co_yield: float = 0.0
    radiative_fraction: float = 0.35
    epumo2: float = 13100.0
    c: Optional[float] = None
    h: Optional[float] = None
    o: Optional[float] = None
    n: Optional[float] = None
    cl: Optional[float] = None
    a: Optional[float] = None
    e: Optional[float] = None
    n_t: Optional[float] = None
    lower_oxygen_limit: float = 0.15
    critical_flame_temperature: float = 1427.0
    auto_ignition_temperature: Optional[float] = None
    # Phase 1 additions
    fuel_radcal_id: Optional[str] = None    # FUEL_RADCAL_ID — radcal fuel surrogate
    check_atom_balance: bool = False        # CHECK_ATOM_BALANCE flag
    soot_h_fraction: Optional[float] = None  # SOOT_H_FRACTION
    # Complex stoichiometry: SPEC_ID_NU(i) / NU(i) (negative = reactant, positive = product)
    spec_id_nu: Optional[List[str]] = None
    nu: Optional[List[float]] = None
    spec_id_n_s: Optional[List[str]] = None  # SPEC_ID_N_S — species with a reaction-order exponent
    n_s: Optional[List[float]] = None        # N_S — exponents for spec_id_n_s

    @property
    def reaction_type(self) -> str:
        """``complex`` when stoichiometry is given species by species, else ``simple`` chemistry."""
        return "complex" if self.spec_id_nu else "simple"


class Surface(FdsEntity):
    """&SURF namelist."""
    name: str = "DefaultSurface"
    color: str = "GRAY"
    rgb: Optional[Tuple[int, int, int]] = None
    emissivity: Optional[float] = None
    backing: str = "VOID"
    layers: List[Layer] = Field(default_factory=list)
    # Fire / heat
    heat_release_rate: Optional[float] = None        # HRRPUA (kW/m²)
    tau_q: Optional[float] = None                    # ramp-up time (s)
    ramp_q: Optional[str] = None                     # RAMP_Q reference
    ramp_t: Optional[str] = None                     # RAMP_T reference
    # Flow
    vel: Optional[float] = None
    volume_flow: Optional[float] = None
    mass_flux: Optional[float] = None
    ramp_v: Optional[str] = None
    # Temperature
    tmp_front: Optional[float] = None
    tmp_back: Optional[float] = None
    # Texture
    texture_map: Optional[str] = None
    texture_width: Optional[float] = None
    texture_height: Optional[float] = None
    # Misc
    transparency: float = 0.0
    burn_away: bool = False
    geometry: str = "CARTESIAN"
    part_id: Optional[str] = None
    matl_id: Optional[str] = None
    heat_transfer_coefficient: Optional[float] = None  # HTC (W/m²/K)
    # Extended SURF fields (PyroSim parity)
    adiabatic: bool = False                            # ADIABATIC — no heat loss
    external_flux: Optional[float] = None              # EXTERNAL_FLUX (kW/m²) — imposed external radiation
    ignition_temperature: Optional[float] = None       # AUTO_IGNITION_TEMPERATURE (°C)
    free_slip: bool = False                            # FREE_SLIP — inviscid (slip) wall BC
    no_slip: bool = False                              # NO_SLIP — explicit viscous (no-slip) wall BC
    tau_t: Optional[float] = None                     # TAU_T — temperature ramp-up time (s)
    roughness: Optional[float] = None                  # ROUGHNESS (m) — wall roughness for log-law
    inner_radius: Optional[float] = None               # INNER_RADIUS (m) — for cylindrical surfaces
    spec_id_surf: Optional[List[str]] = None           # SPEC_ID for species injection at surface
    mass_flux_total: Optional[float] = None            # MASS_FLUX_TOTAL (kg/m²/s) — total mass flux
    ramp_mf: Optional[str] = None                     # RAMP_MF — ramp ID for mass flux
    leak_path: Optional[List[str]] = None              # LEAK_PATH zone pair ['Zone1','Zone2']


class Ramp(FdsEntity):
    """
    &RAMP namelist.

    Each (T, F) pair becomes a separate ``&RAMP ID='name', T=t, F=f /`` line.
    The writer handles expansion.
    """
    name: str = "DefaultRamp"
    times: List[float] = Field(default_factory=list)
    values: List[float] = Field(default_factory=list)
    # Optional activation trigger (first row only in FDS)
    devc_id: Optional[str] = None          # DEVC_ID — device that triggers the ramp
    ctrl_id: Optional[str] = None          # CTRL_ID — control that triggers the ramp
    # Interpolation between data points
    interpolation: Optional[str] = None    # 'LINEAR' (default) or 'QUADRATIC'

    @model_validator(mode="after")
    def check_lengths(self) -> "Ramp":
        if len(self.times) != len(self.values):
            raise ValueError("Ramp times and values must have equal length")
        if len(self.times) > 1:
            for i in range(1, len(self.times)):
                if self.times[i] <= self.times[i - 1]:
                    raise ValueError(
                        f"Ramp times must be strictly increasing "
                        f"(times[{i-1}]={self.times[i-1]} >= times[{i}]={self.times[i]})"
                    )
        return self

    def add_point(self, t: float, f: float) -> None:
        self.times.append(t)
        self.values.append(f)


class Species(FdsEntity):
    """&SPEC namelist."""
    name: str = "DefaultSpec"
    mw: Optional[float] = None
    lumped_component_only: bool = False
    primitive: bool = True
    formula: Optional[str] = None
    vis: Optional[float] = None
    d_ref: Optional[float] = None
    # Lumped-species mixture definition
    spec_id: Optional[List[str]] = None             # component species IDs
    volume_fraction: Optional[List[float]] = None   # VOLUME_FRACTION array
    mass_fraction: Optional[List[float]] = None     # MASS_FRACTION array
    # Radiative properties
    radcal_id: Optional[str] = None                 # RADCAL_ID for radiation
    # Extended SPEC fields (PyroSim parity)
    background: bool = False              # BACKGROUND — this species is the background diluent (N2 by default)
    mass_fraction_0: Optional[float] = None  # MASS_FRACTION_0 — initial ambient mass fraction
    specific_heat: Optional[float] = None  # SPECIFIC_HEAT (kJ/kg/K) — override for non-ideal species
    reference_enthalpy: Optional[float] = None  # REFERENCE_ENTHALPY (kJ/kg) at REFERENCE_TEMPERATURE
    mass_extinction_coefficient: Optional[float] = None  # MASS_EXTINCTION_COEFFICIENT (m2/kg) for smoke visibility
    fic_concentration: Optional[float] = None   # FIC_CONCENTRATION (ppm) irritant dose for FIC/FED


class Particle(FdsEntity):
    """&PART namelist — Lagrangian particle class."""

    @property
    def kind(self) -> str:
        """``tracer`` (massless), ``solid`` (has a surface), else ``droplet`` (liquid, evaporating or not)."""
        if self.massless:
            return "tracer"
        if self.surf_id and not self.spec_id:
            return "solid"
        return "droplet"
    name: str = "DefaultParticle"
    color: str = "BLUE"
    diameter: float = 500.0
    density: float = 1000.0
    drag_law: str = "SPHERE"
    prop_id: Optional[str] = None
    surf_id: Optional[str] = None
    age: Optional[float] = None
    sampling_factor: int = 1
    spec_id: Optional[str] = None
    vaporization_temperature: Optional[float] = None
    heat_of_vaporization: Optional[float] = None
    n_strata: int = 6
    gamma: Optional[float] = None
    sigma: Optional[float] = None
    # Per-particle output tracking
    quantities: Optional[List[str]] = None           # QUANTITIES array (tracked output vars)
    orientation: Optional[Tuple[float,float,float]] = None  # injection direction
    ctrl_id: Optional[str] = None                    # activation control
    # Particle kind (PRT-01): massless tracer, stationary, solid (surf_id) or evaporating droplet (spec_id)
    massless: bool = False                           # MASSLESS - visualisation tracers
    stationary: bool = False                         # STATIONARY - particles that do not move
    monodisperse: bool = False                       # MONODISPERSE - one diameter, no size distribution
    target_only: bool = False                        # TARGET_ONLY - solid particles that only receive heat
    initial_temperature: Optional[float] = None      # INITIAL_TEMPERATURE (deg C)
    minimum_diameter: Optional[float] = None         # MINIMUM_DIAMETER (micron)
    maximum_diameter: Optional[float] = None         # MAXIMUM_DIAMETER (micron)
    free_area_fraction: Optional[float] = None       # FREE_AREA_FRACTION - mesh-like targets
    horizontal_velocity: Optional[float] = None      # HORIZONTAL_VELOCITY (m/s) of solid particles on surfaces
    vertical_velocity: Optional[float] = None        # VERTICAL_VELOCITY (m/s)
