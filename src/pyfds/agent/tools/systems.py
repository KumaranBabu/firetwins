"""Smoke, particles, detector systems, HVAC fan curves and jet fans, fire library, pyrolysis fit, results
summaries and egress outputs (B4)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_NUM = {"type": "number"}
_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}
_STRS = {"type": "array", "items": _STR}
_NUMS = {"type": "array", "items": _NUM}
_PT3 = {"type": "array", "items": _NUM, "minItems": 3, "maxItems": 3}
_MAP_NUM = {"type": "object", "additionalProperties": _NUM}


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


def _names(x):
    return [i.name for i in x] if isinstance(x, (list, tuple)) else x.name


def _parts(d):
    return {k: _names(v) if k not in ("flow", "thrust", "item") else v for k, v in d.items()
            if k not in ("item",)}


TOOLS: List[ToolSpec] = [
    # -- smoke, reactions, particles ------------------------------------------------------
    _spec("get_smoke", "Soot yield per reaction, SOOT mass extinction coefficient and visibility settings.", {}, [],
          lambda api: api.reactions.smoke(), mutates=False),
    _spec("set_smoke", "Custom smoke: mass_extinction_coefficient (m2/kg, default 8700), soot_yield of a reaction, "
          "visibility_factor (3 reflecting sign, 8 light-emitting), maximum_visibility (m).",
          {"mass_extinction_coefficient": _NUM, "soot_yield": _NUM, "reaction": _STR, "visibility_factor": _NUM,
           "maximum_visibility": _NUM}, [], lambda api, **kw: api.reactions.set_smoke(**kw)),
    _spec("get_reaction_table", "Reactants, products and exponents of a reaction as a table.", {"reaction": _STR},
          ["reaction"], lambda api, reaction: api.reactions.stoichiometry(reaction), mutates=False),
    _spec("set_reaction_table", "Replace the species table of a reaction: reactants/products {species: coefficient}.",
          {"reaction": _STR, "reactants": _MAP_NUM, "products": _MAP_NUM, "exponents": _MAP_NUM},
          ["reaction", "reactants", "products"],
          lambda api, reaction, **kw: api.reactions.set_stoichiometry(reaction, **kw).name),
    _spec("add_tracer_particles", "Massless tracer particle class (visualisation).", {"name": _STR, "color": _STR}, [],
          lambda api, **kw: api.particles.add_tracer(**kw).name),
    _spec("add_droplet_particles", "Evaporating liquid droplet class (diameter in micron).",
          {"name": _STR, "diameter": _NUM, "spec_id": _STR, "monodisperse": _BOOL, "minimum_diameter": _NUM,
           "maximum_diameter": _NUM, "initial_temperature": _NUM}, [],
          lambda api, **kw: api.particles.add_droplet(**kw).name),
    _spec("add_solid_particles", "Solid particle class carrying a surface (clutter, embers, vegetation).",
          {"surf_id": _STR, "name": _STR, "diameter": _NUM, "stationary": _BOOL, "target_only": _BOOL}, ["surf_id"],
          lambda api, surf_id, **kw: api.particles.add_solid_particle(surf_id, **kw).name),
    # -- detector systems -----------------------------------------------------------------
    _spec("add_nozzle", "Spray nozzle device (property set must have a particle class); optional control switches it.",
          {"xyz": _PT3, "prop_id": _STR, "ctrl_id": _STR, "name": _STR, "orientation": _PT3}, ["xyz", "prop_id"],
          lambda api, xyz, prop_id, **kw: api.devices.add_nozzle(xyz, prop_id, **kw).name),
    _spec("add_sprinkler_link", "Stand-alone thermal link device (RTI, activation temperature).",
          {"xyz": _PT3, "prop_id": _STR, "rti": _NUM, "activation_temperature": _NUM, "name": _STR}, ["xyz"],
          lambda api, xyz, **kw: api.devices.add_sprinkler_link(xyz, **kw).name),
    _spec("add_dry_pipe_sprinkler", "Sprinkler on a dry pipe: link, TIME_DELAY control and nozzle.",
          {"xyz": _PT3, "nozzle_prop": _STR, "delay": _NUM, "link_prop": _STR, "rti": _NUM,
           "activation_temperature": _NUM, "name": _STR}, ["xyz", "nozzle_prop"],
          lambda api, xyz, nozzle_prop, **kw: _parts(api.devices.add_dry_pipe_sprinkler(xyz, nozzle_prop, **kw))),
    _spec("add_beam_detector", "Beam smoke detector along xb_line [x1,x2,y1,y2,z1,z2]; setpoint in % obscuration.",
          {"xb_line": _NUMS, "setpoint": _NUM, "name": _STR, "quantity": {"type": "string",
           "enum": ["PATH OBSCURATION", "TRANSMISSION"]}}, ["xb_line"],
          lambda api, xb_line, **kw: api.devices.add_beam_detector(xb_line, **kw).name),
    _spec("add_fed_device", "Fractional effective dose (FED) or incapacitating concentration (FIC) at a point.",
          {"xyz": _PT3, "activity": _INT, "quantity": {"type": "string", "enum": ["FED", "FIC"]}, "name": _STR},
          ["xyz"], lambda api, xyz, **kw: api.devices.add_fed_device(xyz, **kw).name),
    _spec("add_aspiration_system", "Aspiration (VESDA) detector: samplers [{xyz, flowrate kg/s, delay s}].",
          {"detector_xyz": _PT3, "samplers": {"type": "array", "items": {"type": "object"}}, "setpoint": _NUM,
           "bypass_flowrate": _NUM, "name": _STR}, ["detector_xyz", "samplers"],
          lambda api, detector_xyz, samplers, **kw: _parts(api.devices.add_aspiration_system(detector_xyz, samplers, **kw))),
    _spec("add_hvac_output", "Output device on an HVAC duct or node (e.g. DUCT VOLUME FLOW, NODE PRESSURE).",
          {"quantity": _STR, "duct_id": _STR, "node_id": {"anyOf": [_STR, _STRS]}, "spec_id": _STR, "cell_l": _NUM,
           "name": _STR}, ["quantity"], lambda api, quantity, **kw: api.devices.add_hvac_output(quantity, **kw).name),
    _spec("add_time_device", "Device that turns on at a simulation time (s).", {"setpoint": _NUM, "name": _STR},
          ["setpoint"], lambda api, setpoint, **kw: api.devices.add_time_device(setpoint, **kw).name),
    _spec("stop_when", "End the run (optionally writing a restart file) when a device or control activates.",
          {"device": _STR, "restart": _BOOL, "name": _STR}, ["device"],
          lambda api, device, **kw: api.devices.stop_when(device, **kw).name),
    _spec("stop_at", "End the run at a simulation time (s) via a time device and a KILL control.",
          {"time": _NUM, "name": _STR}, ["time"], lambda api, time, **kw: api.devices.stop_at(time, **kw).name),
    _spec("update_devices", "Set the same fields on several devices at once (one undo step).",
          {"names": _STRS, "fields": {"type": "object"}}, ["names", "fields"],
          lambda api, names, fields: _names(api.devices.update_many(names, **fields))),
    # -- HVAC -------------------------------------------------------------------------------
    _spec("set_fan_curve", "User fan curve: pressure (Pa) against flow (m3/s); flows increasing, pressure falling.",
          {"fan": _STR, "flows": _NUMS, "pressures": _NUMS, "ramp_id": _STR}, ["fan", "flows", "pressures"],
          lambda api, fan, flows, pressures, **kw: api.fans.set_curve(fan, flows, pressures, **kw).name),
    _spec("get_fan_curve", "How a fan is defined (constant, quadratic or curve points).", {"fan": _STR}, ["fan"],
          lambda api, fan: api.fans.curve(fan), mutates=False),
    _spec("add_jet_fan", "Free-standing jet fan (obstruction, two HVAC vents/nodes, duct, fan). Give flow m3/s or thrust N.",
          {"center": _PT3, "direction": {"type": "string", "enum": ["+x", "-x", "+y", "-y", "+z", "-z"]},
           "width": _NUM, "height": _NUM, "flow": _NUM, "thrust": _NUM, "thickness": _NUM, "name": _STR}, ["center"],
          lambda api, center, **kw: _parts(api.hvac.add_jet_fan(center, **kw))),
    # -- fire library, pool fire --------------------------------------------------------------
    _spec("list_fires", "Fire library: t-squared classes, steady, and curves saved in the project.",
          {"peak_kw": _NUM}, [], lambda api, **kw: api.fires.names(**kw), mutates=False),
    _spec("add_fire_from_library", "Burner from a library fire over xb [x1,x2,y1,y2,z] (ramp + surface + pan).",
          {"item": _STR, "xb": _NUMS, "peak_kw": _NUM, "name": _STR, "pan_height": _NUM, "scale": _NUM},
          ["item", "xb"], lambda api, item, xb, **kw: _parts(api.fires.add_from_library(item, xb, **kw))),
    _spec("save_fire", "Save an HRR curve (times s, hrr_kw) in the project library with its source note.",
          {"name": _STR, "times": _NUMS, "hrr_kw": _NUMS, "description": _STR, "source": _STR},
          ["name", "times", "hrr_kw"], lambda api, name, times, hrr_kw, **kw: api.fires.save_item(name, times, hrr_kw, **kw).name),
    _spec("add_pool_fire", "Liquid pool fire from a liquid-fuel material over xb [x1,x2,y1,y2,z].",
          {"fuel": _STR, "xb": _NUMS, "depth": _NUM, "name": _STR, "pan_height": _NUM}, ["fuel", "xb"],
          lambda api, fuel, xb, **kw: {k: (v if isinstance(v, float) else v.name)
                                       for k, v in api.fires.add_pool_fire(fuel, xb, **kw).items()}),
    # -- materials ---------------------------------------------------------------------------
    _spec("fit_pyrolysis", "Fit Arrhenius A and E to a reaction-rate curve and set them on a material.",
          {"material": _STR, "temperature_c": _NUMS, "rate": _NUMS, "n": _NUM, "remaining_mass": _NUMS,
           "apply": _BOOL}, ["material", "temperature_c", "rate"],
          lambda api, material, temperature_c, rate, **kw: api.materials.fit_pyrolysis(material, temperature_c, rate, **kw)),
    _spec("pyrolysis_from_peak", "A and E from a TGA peak (Kissinger); give activation_energy or other_runs.",
          {"material": _STR, "heating_rate_k_per_min": _NUM, "peak_temperature_c": _NUM, "activation_energy": _NUM,
           "other_runs": {"type": "array", "items": _NUMS}, "n": _NUM, "apply": _BOOL},
          ["material", "heating_rate_k_per_min", "peak_temperature_c"],
          lambda api, material, heating_rate_k_per_min, peak_temperature_c, **kw:
          api.materials.pyrolysis_from_peak(material, heating_rate_k_per_min, peak_temperature_c, **kw)),
    _spec("set_material_byproducts", "Gases (species: yield) and solid residue yield a reacting material gives off.",
          {"material": _STR, "gases": _MAP_NUM, "residue": _NUM}, ["material", "gases"],
          lambda api, material, gases, **kw: api.materials.set_byproducts(material, gases, **kw)),
    # -- results and egress ----------------------------------------------------------------
    _spec("activation_table", "When each device and control first activated, from the FDS output.",
          {"output_dir": _STR, "chid": _STR}, [], lambda api, **kw: api.results.activation_table(**kw), mutates=False),
    _spec("hrr_summary", "Peak HRR, time of peak, total energy and time to reach HRR thresholds.",
          {"output_dir": _STR, "chid": _STR, "thresholds_kw": _NUMS}, [],
          lambda api, **kw: api.results.hrr_summary(**kw), mutates=False),
    _spec("add_egress_outputs", "Add head-height hazard slices (temperature, visibility, CO, CO2, O2) for egress tools.",
          {"height": _NUM}, [], lambda api, **kw: _names(api.egress.add_outputs(**kw))),
    _spec("export_egress_scenario", "Write the egress scenario (exits, groups, tenability limits) as JSON.",
          {"path": _STR, "t_start_evac": _NUM, "groups": {"type": "array", "items": {"type": "object"}},
           "tenability_limits": _MAP_NUM}, ["path"],
          lambda api, path, **kw: api.egress.export(path, **kw), mutates=False),
]
