"""FDS writer part: materials, reactions, species, surfaces, props, controls."""
from __future__ import annotations

from typing import Any, Dict

from pyfds.domain.model import Surface, Material, Reaction, Control, Prop, Species

from .fds_writer_common import _nl


class FdsWriterPhysicsMixin:
    def _write_material(self, obj: Material) -> str:
        d: Dict[str, Any] = {
            "ID":           obj.name,
            "DENSITY":      obj.density,
            "CONDUCTIVITY": obj.conductivity,
            "SPECIFIC_HEAT": obj.specific_heat,
            "EMISSIVITY":   obj.emissivity,
        }
        for k in ("reference_temperature", "heat_of_reaction",
                  "heat_of_combustion", "a", "e", "n_s"):
            v = getattr(obj, k, None)
            if v is not None:
                d[k.upper()] = v
        # P0 fixes — missing scalar fields
        if getattr(obj, "pyrolysis_range", None) is not None: d["PYROLYSIS_RANGE"] = obj.pyrolysis_range
        if getattr(obj, "heating_rate", None) is not None:    d["HEATING_RATE"]    = obj.heating_rate
        if getattr(obj, "reference_rate", None) is not None:  d["REFERENCE_RATE"]  = obj.reference_rate
        if getattr(obj, "nu_gases", None):   # FDS 6.10 knows only NU_SPEC (NU_GASES is rejected)
            d["NU_SPEC"] = obj.nu_gases
        if obj.nu_residue and obj.residue_id:    # FDS 6.10 has no NU_RESIDUE: the residue is a material
            d["NU_MATL"] = obj.nu_residue
            d["MATL_ID"] = obj.residue_id
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
            n_s_vals = [r.n_s for r in obj.reactions]
            if all(v is not None for v in n_s_vals):         # one order per reaction, or none
                d["N_S"] = n_s_vals
            if nu_spec_vals: d["NU_SPEC"]          = nu_spec_vals
        return _nl("MATL", d)

    def _write_reaction(self, obj: Reaction) -> str:
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.fuel:          d["FUEL"] = obj.fuel
        if obj.formula:       d["FORMULA"] = obj.formula
        if obj.heat_of_combustion:                 # 0 means "not given": FDS then uses the fuel's own value
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
        if getattr(obj, "mass_extinction_coefficient", None) is not None: d["MASS_EXTINCTION_COEFFICIENT"] = obj.mass_extinction_coefficient
        if getattr(obj, "fic_concentration", None) is not None:           d["FIC_CONCENTRATION"]           = obj.fic_concentration
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
        if getattr(obj, "k_factor", None) is not None:                 d["K_FACTOR"]                = obj.k_factor
        if getattr(obj, "orifice_diameter", None) is not None:         d["ORIFICE_DIAMETER"]        = obj.orifice_diameter
        if getattr(obj, "pressure_ramp", None):                        d["PRESSURE_RAMP"]           = obj.pressure_ramp
        if getattr(obj, "fed_activity", None) is not None:             d["FED_ACTIVITY"]            = obj.fed_activity
        return _nl("PROP", d)

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
