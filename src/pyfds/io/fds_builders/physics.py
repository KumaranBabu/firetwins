"""Physics namelists: SURF, MATL, REAC, PART, SPEC, INIT, WIND.

Mixin for ``FdsParser``: each ``_parse_<tag>`` turns one tokenised record into entities.
"""
from __future__ import annotations

import logging
from typing import Dict
from pyfds.core.exceptions import FdsParseError
from pyfds.domain.model import FdsProject, Surface, Reaction, Particle, Species, Init, WindProfile

logger = logging.getLogger(__name__)


class PhysicsBuilders:
    def _parse_surf(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"SURF_{len(p.surfaces)}")
        # Parse leak_path — FDS: LEAK_PATH='Zone1','Zone2'
        leak_raw = d.get("LEAK_PATH", None)
        leak_path = None
        if leak_raw:
            parts = [x.strip().strip("'\"") for x in str(leak_raw).split(",")]
            leak_path = [x for x in parts if x]
        # Parse SPEC_ID for surface injection (may be comma-separated)
        spec_id_raw = d.get("SPEC_ID", None)
        spec_id_surf = None
        if spec_id_raw:
            parts = [x.strip().strip("'\"") for x in str(spec_id_raw).split(",")]
            spec_id_surf = [x for x in parts if x] or None
        # layers: MATL_ID + THICKNESS lists of equal length; a lone MATL_ID is just the material
        layers, matl_id = [], None
        ids_raw, thick_raw = dict.get(d, "MATL_ID"), dict.get(d, "THICKNESS")
        if ids_raw is not None:
            ids = self._strs(d, "MATL_ID") or []
            thick = self._floats(d, "THICKNESS") if thick_raw is not None else None
            if thick and len(thick) == len(ids):
                from pyfds.domain.model import Layer
                layers = [Layer(material_id=m, thickness=t) for m, t in zip(ids, thick)]
            elif len(ids) == 1 and thick_raw is None:
                matl_id = ids[0]
            else:                                  # unusual shape: keep the text as it was
                d.used.discard("MATL_ID"); d.used.discard("THICKNESS")
        rgb = self._floats(d, "RGB")
        s = Surface(
            name=name,
            layers=layers,
            matl_id=matl_id,
            volume_flow=self._flt(d, "VOLUME_FLOW"),
            mass_flux=self._flt(d, "MASS_FLUX"),
            ramp_t=self._str(d, "RAMP_T") or None,
            ramp_v=self._str(d, "RAMP_V") or None,
            tmp_back=self._flt(d, "TMP_BACK"),
            transparency=self._flt(d, "TRANSPARENCY", 0.0),
            part_id=self._str(d, "PART_ID") or None,
            rgb=tuple(int(v) for v in rgb) if rgb and len(rgb) == 3 else None,
            texture_width=self._flt(d, "TEXTURE_WIDTH"),
            texture_height=self._flt(d, "TEXTURE_HEIGHT"),
            color=self._str(d, "COLOR", "GRAY"),
            heat_release_rate=self._flt(d, "HRRPUA"),
            tau_q=self._flt(d, "TAU_Q"),
            ramp_q=self._str(d, "RAMP_Q") or None,
            tmp_front=self._flt(d, "TMP_FRONT"),
            vel=self._flt(d, "VEL"),
            emissivity=self._flt(d, "EMISSIVITY"),
            backing=self._str(d, "BACKING", "VOID"),
            texture_map=self._str(d, "TEXTURE_MAP") or None,
            burn_away=self._bool(d, "BURN_AWAY"),
            heat_transfer_coefficient=self._flt(d, "HEAT_TRANSFER_COEFFICIENT"),
            # Extended SURF fields
            adiabatic=self._bool(d, "ADIABATIC"),
            external_flux=self._flt(d, "EXTERNAL_FLUX"),
            ignition_temperature=self._flt(d, "AUTO_IGNITION_TEMPERATURE"),
            free_slip=self._bool(d, "FREE_SLIP"),
            no_slip=self._bool(d, "NO_SLIP"),
            tau_t=self._flt(d, "TAU_T"),
            roughness=self._flt(d, "ROUGHNESS"),
            inner_radius=self._flt(d, "INNER_RADIUS"),
            spec_id_surf=spec_id_surf,
            mass_flux_total=self._flt(d, "MASS_FLUX_TOTAL"),
            ramp_mf=self._str(d, "RAMP_MF") or None,
            leak_path=leak_path,
        )
        p.add_entity(s)

    def _parse_matl(self, p: FdsProject, d: Dict) -> None:
        from pyfds.domain.model import Material, MaterialReaction
        name = self._str(d, "ID", f"MATL_{len(p.materials)}")
        n_reactions = self._int(d, "N_REACTIONS", 1)
        # Parse per-reaction arrays (A, E, HEAT_OF_REACTION) if N_REACTIONS > 1
        reactions = []
        if n_reactions and n_reactions > 1:
            a_vals  = self._floats(d, "A")   or []
            e_vals  = self._floats(d, "E")   or []
            hor_vals = self._floats(d, "HEAT_OF_REACTION") or []
            for i in range(n_reactions):
                rxn = MaterialReaction(
                    a=a_vals[i] if i < len(a_vals) else None,
                    e=e_vals[i] if i < len(e_vals) else None,
                    heat_of_reaction=hor_vals[i] if i < len(hor_vals) else None,
                )
                reactions.append(rxn)
        p.add_entity(Material(
            name=name,
            density=self._flt(d, "DENSITY", 1000.0),
            conductivity=self._flt(d, "CONDUCTIVITY", 0.5),
            specific_heat=self._flt(d, "SPECIFIC_HEAT", 1.0),
            emissivity=self._flt(d, "EMISSIVITY", 0.9),
            reference_temperature=self._flt(d, "REFERENCE_TEMPERATURE"),
            heat_of_reaction=self._flt(d, "HEAT_OF_REACTION"),
            heat_of_combustion=self._flt(d, "HEAT_OF_COMBUSTION"),
            a=self._flt(d, "A"),
            e=self._flt(d, "E"),
            n_s=self._flt(d, "N_S"),
            nu_residue=self._flt(d, "NU_RESIDUE"),
            n_reactions=n_reactions or 1,
            reactions=reactions,
            conductivity_ramp=self._str(d, "CONDUCTIVITY_RAMP") or None,
            specific_heat_ramp=self._str(d, "SPECIFIC_HEAT_RAMP") or None,
            absorption_coefficient=self._flt(d, "ABSORPTION_COEFFICIENT"),
            boiling_temperature=self._flt(d, "BOILING_TEMPERATURE"),
            spec_ids=self._strs(d, "SPEC_ID"),
            nu_gases=self._floats(d, "NU_GASES") or (self._floats(d, "NU_SPEC") if "BOILING_TEMPERATURE" in d else None),
        ))

    def _parse_reac(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"REAC_{len(p.reactions)}")
        p.add_entity(Reaction(
            name=name,
            fuel=self._str(d, "FUEL") or None,
            formula=self._str(d, "FORMULA") or None,
            heat_of_combustion=self._flt(d, "HEAT_OF_COMBUSTION", 0.0),
            soot_yield=self._flt(d, "SOOT_YIELD", 0.0),
            co_yield=self._flt(d, "CO_YIELD", 0.0),
            radiative_fraction=self._flt(d, "RADIATIVE_FRACTION", 0.35),
            epumo2=self._flt(d, "EPUMO2", 13100.0),
            # Phase 1 additions
            fuel_radcal_id=self._str(d, "FUEL_RADCAL_ID") or None,
            check_atom_balance=self._bool(d, "CHECK_ATOM_BALANCE"),
            soot_h_fraction=self._flt(d, "SOOT_H_FRACTION"),
            spec_id_nu=self._indexed(d, "SPEC_ID_NU", str),
            nu=self._indexed(d, "NU", float),
            spec_id_n_s=self._indexed(d, "SPEC_ID_N_S", str),
            n_s=self._indexed(d, "N_S", float),
        ))

    def _parse_part(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"PART_{len(p.particles)}")
        p.add_entity(Particle(
            name=name,
            color=self._str(d, "COLOR", "BLUE"),
            diameter=self._flt(d, "DIAMETER", 500.0),
            density=self._flt(d, "DENSITY", 1000.0),
            drag_law=self._str(d, "DRAG_LAW", "SPHERE"),
            prop_id=self._str(d, "PROP_ID") or None,
            surf_id=self._str(d, "SURF_ID") or None,
            sampling_factor=self._int(d, "SAMPLING_FACTOR", 1),
            massless=self._bool(d, "MASSLESS"),
            stationary=self._bool(d, "STATIONARY"),
            monodisperse=self._bool(d, "MONODISPERSE"),
            target_only=self._bool(d, "TARGET_ONLY"),
            initial_temperature=self._flt(d, "INITIAL_TEMPERATURE"),
            minimum_diameter=self._flt(d, "MINIMUM_DIAMETER"),
            maximum_diameter=self._flt(d, "MAXIMUM_DIAMETER"),
            free_area_fraction=self._flt(d, "FREE_AREA_FRACTION"),
            horizontal_velocity=self._flt(d, "HORIZONTAL_VELOCITY"),
            vertical_velocity=self._flt(d, "VERTICAL_VELOCITY"),
        ))

    def _parse_spec(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"SPEC_{len(p.species)}")
        # Parse component SPEC_ID array for lumped species
        spec_id_raw = d.get("SPEC_ID", None)
        spec_ids = None
        if spec_id_raw:
            parts = [s.strip().strip("'\"") for s in spec_id_raw.split(",") if s.strip()]
            spec_ids = parts if parts else None
        p.add_entity(Species(
            name=name,
            mw=self._flt(d, "MW"),
            formula=self._str(d, "FORMULA") or None,
            spec_id=spec_ids,
            volume_fraction=self._floats(d, "VOLUME_FRACTION"),
            mass_fraction=self._floats(d, "MASS_FRACTION"),
            radcal_id=self._str(d, "RADCAL_ID") or None,
            primitive=self._bool(d, "PRIMITIVE", True),
            lumped_component_only=self._bool(d, "LUMPED_COMPONENT_ONLY"),
            # Extended SPEC fields
            background=self._bool(d, "BACKGROUND"),
            mass_fraction_0=self._flt(d, "MASS_FRACTION_0"),
            specific_heat=self._flt(d, "SPECIFIC_HEAT"),
            reference_enthalpy=self._flt(d, "REFERENCE_ENTHALPY"),
            mass_extinction_coefficient=self._flt(d, "MASS_EXTINCTION_COEFFICIENT"),
            fic_concentration=self._flt(d, "FIC_CONCENTRATION"),
        ))

    def _parse_init(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"INIT_{len(p.inits)}")
        xb = self._parse_xb(d.get("XB", "0,1,0,1,0,1"))
        shape = self._str(d, "SHAPE", "BLOCK").upper() or "BLOCK"
        xyz_center = None
        if "XYZ" in d:                       # point source / shape centre
            try:
                xyz_center = self._parse_xyz(d["XYZ"])
            except FdsParseError:
                pass
        # Multi-species: SPEC_ID may be a comma-separated list
        spec_id_raw = d.get("SPEC_ID", None)
        spec_ids_list = None
        spec_id_scalar = None
        if spec_id_raw:
            parts = [s.strip().strip("'\"") for s in spec_id_raw.split(",") if s.strip()]
            if len(parts) > 1:
                spec_ids_list = parts
            elif parts:
                spec_id_scalar = parts[0]
        # MASS_FRACTION may also be a comma-separated list
        mf_raw = d.get("MASS_FRACTION", None)
        mass_fractions_list = None
        mass_fraction_scalar = None
        if mf_raw:
            mf_parts = [s.strip() for s in mf_raw.split(",") if s.strip()]
            if len(mf_parts) > 1:
                try:
                    mass_fractions_list = [float(v) for v in mf_parts]
                except ValueError:
                    pass
            elif mf_parts:
                try:
                    mass_fraction_scalar = float(mf_parts[0])
                except ValueError:
                    pass
        p.add_entity(Init(
            name=name, x_min=xb[0], x_max=xb[1],
            y_min=xb[2], y_max=xb[3], z_min=xb[4], z_max=xb[5],
            temperature=self._flt(d, "TEMPERATURE"),
            density=self._flt(d, "DENSITY"),
            mass_fraction=mass_fraction_scalar,
            spec_id=spec_id_scalar,
            spec_ids=spec_ids_list,
            mass_fractions=mass_fractions_list,
            n_particles=self._int(d, "N_PARTICLES"),
            part_id=self._str(d, "PART_ID") or None,
            shape=shape,
            radius=self._flt(d, "RADIUS"),
            xyz_center=xyz_center,
        ))

    def _parse_wind(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"WIND_{len(p.wind_profiles)}")
        p.add_entity(WindProfile(
            name=name,
            speed=self._flt(d, "SPEED", 0.0),
            direction=self._flt(d, "DIRECTION", 270.0),
            z_ref=self._flt(d, "Z_REF", 10.0),
            z0=self._flt(d, "Z_0", self._flt(d, "Z0")),
            l=self._flt(d, "L"),
            ramp_id=self._str(d, "RAMP_SPEED_T") or self._str(d, "RAMP_ID") or None,
            ramp_direction=self._str(d, "RAMP_DIRECTION_T") or None,
            latitude=self._flt(d, "LATITUDE"),
            ground_level=self._flt(d, "GROUND_LEVEL"),
            lapse_rate=self._flt(d, "LAPSE_RATE"),
            stratification=self._bool(d, "STRATIFICATION", None),
            theta_star=self._flt(d, "THETA_STAR"),
        ))
