"""
Unit tests — agent tool layer (src/pyfds/agent).

Verifies:
  1. Registry integrity (unique names, well-formed JSON Schema, callable handlers)
  2. Dispatcher renders the Anthropic tool-list format from the registry
  3. End-to-end tool calls go through FdsApi (mutations are undo-able, results
     are JSON-serializable) — i.e. the agent path behaves identically to the
     human/GUI path since both call the same manager methods.
"""
from __future__ import annotations

import pytest


def _make_api():
    from pyfds.api import FdsApi
    return FdsApi()


# ===========================================================================
# 1. Registry integrity
# ===========================================================================

def test_tool_names_are_unique():
    from pyfds.agent import TOOL_REGISTRY
    names = [t.name for t in TOOL_REGISTRY]
    assert len(names) == len(set(names))


def test_every_tool_has_well_formed_schema_and_handler():
    from pyfds.agent import TOOL_REGISTRY
    for t in TOOL_REGISTRY:
        assert t.name
        assert t.description
        assert t.input_schema.get("type") == "object"
        assert "properties" in t.input_schema
        assert callable(t.handler)


def test_get_tool_unknown_raises():
    from pyfds.agent.registry import get_tool
    with pytest.raises(KeyError):
        get_tool("does_not_exist")


# ===========================================================================
# 2. Dispatcher rendering
# ===========================================================================

def test_anthropic_tools_shape():
    from pyfds.agent import AgentToolDispatcher, TOOL_REGISTRY
    dispatcher = AgentToolDispatcher(_make_api())
    tools = dispatcher.anthropic_tools()
    assert len(tools) == len(TOOL_REGISTRY)
    for tool in tools:
        assert set(tool.keys()) == {"name", "description", "input_schema"}


def test_call_unknown_tool_raises():
    from pyfds.agent import AgentToolDispatcher
    dispatcher = AgentToolDispatcher(_make_api())
    with pytest.raises(KeyError):
        dispatcher.call("does_not_exist", {})


# ===========================================================================
# 3. End-to-end: agent path == GUI/human path (same FdsApi calls)
# ===========================================================================

def test_add_mesh_via_dispatcher_matches_direct_api_call():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    result = dispatcher.call("add_mesh", {"ijk": [10, 10, 5], "xb": [0, 4, 0, 4, 0, 2], "name": "m1"})

    assert result["name"] == "m1"
    assert len(api.meshes.all()) == 1
    assert api.meshes.all()[0].name == "m1"


def test_add_vent_and_add_hole_via_dispatcher():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    vent = dispatcher.call("add_vent", {"xb": [0, 1, 0, 1, 2, 2], "surf_id": "BURNER", "name": "v1"})
    assert vent["surface_id"] == "BURNER"
    assert api.vents.get("v1") is not None

    hole = dispatcher.call("add_hole", {"xb": [0, 1, 0, 1, 0, 1], "name": "h1"})
    assert hole["name"] == "h1"
    assert api.holes.get("h1") is not None

    dispatcher.call("remove_vent", {"name": "v1"})
    dispatcher.call("remove_hole", {"name": "h1"})
    assert api.vents.count() == 0
    assert api.holes.count() == 0


def test_output_entity_tools_via_dispatcher():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    dispatcher.call("add_slice", {"quantity": "TEMPERATURE", "plane": "Z", "position": 1.5, "name": "s1"})
    dispatcher.call("add_boundary_file", {"quantity": "WALL TEMPERATURE", "name": "b1"})
    dispatcher.call("add_isosurface", {"quantity": "TEMPERATURE", "value": 60.0, "name": "i1"})
    dispatcher.call("add_plot3d", {"quantity": "TEMPERATURE", "name": "p1"})

    assert api.slices.get("s1") is not None
    assert api.bndfs.get("b1") is not None
    assert api.isofs.get("i1") is not None
    assert api.plot3ds.get("p1") is not None

    assert [s["name"] for s in dispatcher.call("list_slices", {})] == ["s1"]

    dispatcher.call("remove_slice", {"name": "s1"})
    dispatcher.call("remove_boundary_file", {"name": "b1"})
    dispatcher.call("remove_isosurface", {"name": "i1"})
    dispatcher.call("remove_plot3d", {"name": "p1"})
    assert api.slices.count() == 0 and api.bndfs.count() == 0
    assert api.isofs.count() == 0 and api.plot3ds.count() == 0


def test_hvac_network_tools_via_dispatcher():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    dispatcher.call("add_hvac_node", {"xyz": [0, 0, 0], "ambient": True, "name": "amb1"})
    dispatcher.call("add_hvac_node", {"xyz": [5, 0, 0], "name": "room1"})
    dispatcher.call("add_hvac_duct", {"node_id_1": "amb1", "node_id_2": "room1", "diameter": 0.3, "name": "duct1"})
    dispatcher.call("add_fan", {"duct_id": "duct1", "volume_flow_rate": 1.0, "name": "fan1"})
    dispatcher.call("add_damper", {"duct_id": "duct1", "ctrl_id": "ctrl1", "name": "damper1"})
    dispatcher.call("add_hvac_filter", {"duct_id": "duct1", "efficiency": 0.95, "name": "filter1"})
    dispatcher.call("add_hvac_leakage", {"zone_id_1": "z1", "zone_id_2": "z2", "area": 0.002, "name": "leak1"})

    assert api.hvac_nodes.get("amb1").ambient is True
    assert api.hvac_ducts.get("duct1").diameter == 0.3
    assert api.fans.get("fan1").volume_flow_rate == 1.0
    assert api.dampers.get("damper1").ctrl_id == "ctrl1"
    assert api.hvac_filters.get("filter1").efficiency == 0.95
    assert api.hvac_leakages.get("leak1").area == 0.002

    assert [n["name"] for n in dispatcher.call("list_hvac_nodes", {})] == ["amb1", "room1"]

    dispatcher.call("remove_hvac_node", {"name": "amb1"})
    dispatcher.call("remove_hvac_duct", {"name": "duct1"})
    dispatcher.call("remove_fan", {"name": "fan1"})
    dispatcher.call("remove_damper", {"name": "damper1"})
    dispatcher.call("remove_hvac_filter", {"name": "filter1"})
    dispatcher.call("remove_hvac_leakage", {"name": "leak1"})
    assert api.hvac_nodes.count() == 1  # room1 still there
    assert api.hvac_ducts.count() == 0


def test_init_particle_prof_tools_via_dispatcher():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    dispatcher.call("add_particle_class", {"diameter": 200.0, "name": "water_droplet"})
    dispatcher.call("add_init", {"xb": [0, 2, 0, 2, 0, 2], "temperature": 25.0, "name": "init1"})
    dispatcher.call("add_init", {
        "xb": [0, 1, 0, 1, 0, 1], "part_id": "water_droplet", "n_particles": 1000, "name": "cloud1",
    })
    dispatcher.call("add_profile", {"quantity": "TEMPERATURE", "xyz": [1.0, 2.0, 0.0], "name": "prof1"})

    assert api.particles.get("water_droplet").diameter == 200.0
    assert api.inits.get("init1").temperature == 25.0
    cloud = api.inits.get("cloud1")
    assert cloud.part_id == "water_droplet"
    assert cloud.n_particles == 1000
    assert api.profs.get("prof1").quantity == "TEMPERATURE"

    assert [n["name"] for n in dispatcher.call("list_inits", {})] == ["init1", "cloud1"]
    assert [n["name"] for n in dispatcher.call("list_particle_classes", {})] == ["water_droplet"]
    assert [n["name"] for n in dispatcher.call("list_profiles", {})] == ["prof1"]

    dispatcher.call("remove_init", {"name": "init1"})
    dispatcher.call("remove_particle_class", {"name": "water_droplet"})
    dispatcher.call("remove_profile", {"name": "prof1"})
    assert api.inits.count() == 1  # cloud1 still there
    assert api.particles.count() == 0
    assert api.profs.count() == 0


def test_scenario_tools_via_dispatcher(tmp_path):
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="obst1")

    dispatcher.call("create_scenario", {"name": "low", "description": "500kW case"})
    dispatcher.call("create_scenario", {"name": "high"})
    dispatcher.call("clone_scenario", {"base_name": "low", "new_name": "low_clone"})
    dispatcher.call("add_scenario_override", {
        "scenario_name": "low", "entity_name": "obst1", "field_name": "x_max", "value": 3.0,
    })

    assert [s["name"] for s in dispatcher.call("list_scenarios", {})] == ["low", "high", "low_clone"]

    dispatcher.call("apply_scenario", {"name": "low"})
    assert api.obstructions.get("obst1").x_max == 3.0
    dispatcher.call("reset_scenario", {})
    assert api.obstructions.get("obst1").x_max == 1.0

    written = dispatcher.call("export_scenarios", {"dirpath": str(tmp_path)})
    assert set(written.keys()) == {"low", "high", "low_clone"}
    assert api.scenarios.active is None

    dispatcher.call("delete_scenario", {"name": "low_clone"})
    assert api.scenarios.get("low_clone") is None


def test_floor_tools_via_dispatcher(tmp_path):
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ground_box")

    dispatcher.call("define_floor", {"name": "Ground", "z_min": 0.0, "z_max": 3.0})
    dispatcher.call("define_floor", {"name": "Level 1", "z_min": 3.0, "z_max": 6.0})
    dispatcher.call("assign_entity_to_floor", {"entity_name": "ground_box", "floor_name": "Ground"})

    assert [f["name"] for f in dispatcher.call("list_floors", {})] == ["Ground", "Level 1"]
    assert api.floors.floor_of(api.obstructions.get("ground_box")).name == "Ground"

    path = tmp_path / "floors.json"
    dispatcher.call("export_floors", {"filepath": str(path)})
    assert path.exists()

    api2 = _make_api()
    api2.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ground_box")
    dispatcher2 = AgentToolDispatcher(api2)
    count = dispatcher2.call("import_floors", {"filepath": str(path)})
    assert count == 1
    assert api2.floors.floor_of(api2.obstructions.get("ground_box")).name == "Ground"

    dispatcher.call("delete_floor", {"name": "Level 1"})
    assert api.floors.get_floor("Level 1") is None

    count2 = dispatcher.call("auto_assign_floors", {})
    assert isinstance(count2, int)


def test_configure_simulation_params_via_dispatcher_is_undoable():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)
    original_t_end = api.project.params.t_end

    dispatcher.call("configure_simulation_params", {
        "t_end": 300.0, "t_begin": 10.0, "dt": 0.5, "restrict_time_step": False,
    })

    assert api.project.params.t_end == 300.0
    assert api.project.params.t_begin == 10.0
    assert api.project.params.dt == 0.5
    assert api.project.params.restrict_time_step is False

    # 3 separate commands were pushed (set_timing + 2x set_property) — undo
    # all of them and confirm t_end reverts to its original value.
    api.history.undo()
    api.history.undo()
    api.history.undo()
    assert api.project.params.t_end == original_t_end


def test_add_surface_from_library_via_dispatcher():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    result = dispatcher.call("add_surface_from_library", {"preset_name": "gypsum_wall_12mm"})

    assert result["name"] == "GYPSUM_WALL_12MM"
    assert api.surfaces.count() == 1


def test_library_tool_schemas_expose_real_preset_names_as_enums():
    from pyfds.agent.registry import get_tool

    material_enum = get_tool("add_material_from_library").input_schema["properties"]["preset_name"]["enum"]
    surface_enum = get_tool("add_surface_from_library").input_schema["properties"]["preset_name"]["enum"]
    fuel_enum = get_tool("add_fuel_reaction").input_schema["properties"]["fuel_name"]["enum"]

    assert "concrete" in material_enum
    assert "gypsum_wall_12mm" in surface_enum
    assert len(fuel_enum) > 0


def test_add_device_via_dispatcher_uses_generic_quantity():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    result = dispatcher.call("add_device", {"quantity": "VISIBILITY", "xyz": [1, 1, 2], "name": "smoke01"})

    assert result["name"] == "smoke01"
    assert result["quantity"] == "VISIBILITY"
    assert api.devices.get("smoke01") is not None


def test_add_and_list_and_remove_obstruction():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    dispatcher.call("add_obstruction", {"xb": [0, 1, 0, 4, 0, 3], "surf_id": "INERT", "name": "wall1"})
    listed = dispatcher.call("list_obstructions", {})
    assert any(o["name"] == "wall1" for o in listed)

    dispatcher.call("move_obstruction", {"name": "wall1", "dx": 2.0})
    moved = api.obstructions.get("wall1")
    assert moved.x_min == pytest.approx(2.0)

    dispatcher.call("remove_obstruction", {"name": "wall1"})
    assert api.obstructions.get("wall1") is None


def test_remove_nonexistent_obstruction_raises():
    from pyfds.agent import AgentToolDispatcher
    dispatcher = AgentToolDispatcher(_make_api())
    with pytest.raises(KeyError):
        dispatcher.call("remove_obstruction", {"name": "ghost"})


def test_mutations_are_undoable_through_history_manager():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    dispatcher.call("add_obstruction", {"xb": [0, 1, 0, 1, 0, 1], "name": "box"})
    assert api.obstructions.get("box") is not None

    dispatcher.call("undo", {})
    assert api.obstructions.get("box") is None

    dispatcher.call("redo", {})
    assert api.obstructions.get("box") is not None


def test_advisory_engineering_tools_do_not_mutate_project():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    before = len(api.meshes.all())
    result = dispatcher.call("characterise_fire", {"hrr_kw": 1000.0, "growth": "MEDIUM"})
    assert isinstance(result, dict)
    assert len(api.meshes.all()) == before


def test_mesh_wizard_adds_a_mesh_sized_for_the_fire():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    dispatcher.call("mesh_wizard", {
        "hrr_kw": 1000.0,
        "room_xb": [0, 5, 0, 5, 0, 3],
        "target_cells_millions": 0.5,
    })
    assert len(api.meshes.all()) == 1


def test_validate_project_is_read_only_and_returns_report():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)
    report = dispatcher.call("validate_project", {})
    assert report is not None


def test_project_info_returns_string():
    from pyfds.agent import AgentToolDispatcher
    dispatcher = AgentToolDispatcher(_make_api())
    info = dispatcher.call("project_info", {})
    assert isinstance(info, str)
    assert "CHID" in info


def test_list_fuels_and_add_fuel_reaction():
    from pyfds.agent import AgentToolDispatcher
    api = _make_api()
    dispatcher = AgentToolDispatcher(api)

    fuels = dispatcher.call("list_fuels", {})
    assert isinstance(fuels, list)
    assert len(fuels) > 0

    dispatcher.call("add_fuel_reaction", {"fuel_name": fuels[0]})
    assert len(api.reactions.all()) == 1
