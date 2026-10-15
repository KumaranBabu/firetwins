"""P0 partial rows, batch 1: typed surfaces (SRF-01), liquid fuel (MAT-03), complex stoichiometry (RXN-01),
aircoil (HVC-01), gravity ramps and ambient conditions (SIM-03)."""
from __future__ import annotations

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.domain import surface_types as st
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="M")
    return a


def _roundtrip(api, tmp_path):
    f = tmp_path / "x.fds"
    FdsWriter().write(api.project, str(f))
    return f.read_text(), FdsParser().parse(str(f))


# -- SRF-01 ----------------------------------------------------------------------------------
@pytest.mark.parametrize("kind,fields,expect", [
    ("basic", {}, "basic"),
    ("burner", {"heat_release_rate": 500.0}, "burner"),
    ("supply", {"flow": 0.5}, "supply"),
    ("exhaust", {"flow": 0.5}, "exhaust"),
    ("supply", {"volume_flow": 0.2}, "supply"),
    ("heater_cooler", {"tmp_front": 80.0}, "heater_cooler"),
])
def test_typed_surface_round_trips_its_kind(api, kind, fields, expect):
    s = api.surfaces.add_typed(kind, name=f"S_{kind}", **fields)
    assert api.surfaces.kind(s) == expect == st.kind_of(s)


def test_supply_is_negative_exhaust_positive(api):
    assert api.surfaces.add_typed("supply", flow=0.5).vel == -0.5
    assert api.surfaces.add_typed("exhaust", flow=0.5).vel == 0.5


def test_layered_and_air_leak(api):
    from pyfds.domain.material_presets import list_surface_presets
    api.surfaces.add_from_library(next(iter(list_surface_presets())))
    assert any(api.surfaces.kind(s) == "layered" for s in api.surfaces.all())
    api.zones.add_zone([0.2, 0.2, 0.2], name="Z1")
    api.zones.add_zone([0.8, 0.8, 0.8], name="Z2")
    leak = api.surfaces.add_typed("air_leak", leak_path=["Z1", "Z2"])
    assert api.surfaces.kind(leak) == "air_leak"


@pytest.mark.parametrize("kind,fields", [
    ("burner", {}), ("burner", {"heat_release_rate": -1}), ("supply", {}), ("supply", {"flow": -1}),
    ("heater_cooler", {}), ("layered", {}), ("air_leak", {"leak_path": ["only"]}), ("basic", {"vel": 1.0}),
    ("nonsense", {}),
])
def test_typed_surface_rejects_bad_input(api, kind, fields):
    with pytest.raises(ValueError):
        api.surfaces.add_typed(kind, **fields)
    assert not api.surfaces.all()


def test_air_leak_needs_existing_zones(api):
    with pytest.raises(KeyError):
        api.surfaces.add_typed("air_leak", leak_path=["A", "B"])


def test_mixed_surface_is_general_and_flagged(api):
    from pyfds.domain.model import Surface
    s = Surface(name="MIX", heat_release_rate=100.0, tmp_front=50.0, vel=1.0, volume_flow=2.0)
    api.surfaces.add(s)
    assert api.surfaces.kind(s) == "general"
    rep = api.validation.validate()
    assert any(r.rule == "SurfaceType" for r in rep.results)


def test_typed_surface_is_one_undo_step(api):
    api.surfaces.add_typed("burner", heat_release_rate=100.0)
    api.history.undo()
    assert not api.surfaces.all()


# -- MAT-03 ----------------------------------------------------------------------------------
def test_liquid_fuel_round_trip(api, tmp_path):
    m = api.materials.add_liquid_fuel("HEPTANE", "N-HEPTANE", boiling_temperature=98.0, heat_of_vaporization=365.0,
                                      density=684.0, specific_heat=2.2)
    assert api.materials.is_liquid_fuel(m)
    text, back = _roundtrip(api, tmp_path)
    assert "BOILING_TEMPERATURE" in text and "NU_SPEC" in text and "SPEC_ID='N-HEPTANE'" in text
    b = back.materials[0]
    assert b.boiling_temperature == 98.0 and b.spec_ids == ["N-HEPTANE"] and b.nu_gases == [1.0]
    assert b.heat_of_reaction == 365.0


@pytest.mark.parametrize("bad", [{"boiling_temperature": 0}, {"heat_of_vaporization": -1}, {"density": 0}])
def test_liquid_fuel_rejects_non_positive(api, bad):
    args = dict(name="L", fuel_species="METHANOL", boiling_temperature=65.0, heat_of_vaporization=1100.0,
                density=790.0, specific_heat=2.5)
    args.update(bad)
    with pytest.raises(ValueError):
        api.materials.add_liquid_fuel(**args)


def test_liquid_fuel_rule_flags_incomplete_material(api):
    from pyfds.domain.model import Material
    api.materials.add(Material(name="BAD", boiling_temperature=80.0))
    rules = [r for r in api.validation.validate().results if r.rule == "LiquidFuel"]
    assert len(rules) == 2                                   # no vaporisation heat, no species


def test_solid_material_unaffected_by_new_parsing(api, tmp_path):
    from pyfds.domain.model import Material
    api.materials.add(Material(name="WOOD", nu_gases=[0.8], spec_ids=["PROPANE"]))
    text, back = _roundtrip(api, tmp_path)
    assert "NU_SPEC" in text and "NU_GASES" not in text
    assert back.materials[0].nu_gases == [0.8]


# -- RXN-01 ----------------------------------------------------------------------------------
def test_complex_reaction_round_trip(api, tmp_path):
    r = api.reactions.add_complex_reaction({"PROPANE": 1, "OXYGEN": 5}, {"CARBON DIOXIDE": 3, "WATER VAPOR": 4},
                                           name="PROP", exponents={"PROPANE": 1.0})
    assert r.reaction_type == "complex" and api.reactions.reaction_type("PROP") == "complex"
    assert r.nu == [-1, -5, 3, 4]
    text, back = _roundtrip(api, tmp_path)
    assert "SPEC_ID_NU=" in text and "NU=-1" in text
    b = back.reactions[0]
    assert b.spec_id_nu == ["PROPANE", "OXYGEN", "CARBON DIOXIDE", "WATER VAPOR"] and b.nu == [-1, -5, 3, 4]
    assert b.spec_id_n_s == ["PROPANE"] and b.n_s == [1.0]


def test_simple_reaction_is_simple(api):
    r = api.reactions.add_simple_reaction("PROPANE", 46000.0)
    assert r.reaction_type == "simple"


@pytest.mark.parametrize("react,prod", [
    ({"PROPANE": 1, "OXYGEN": 5}, {"CARBON DIOXIDE": 3}),            # mass not balanced
    ({"PROPANE": 1, "MYSTERY": 5}, {"CARBON DIOXIDE": 3}),           # unknown species
    ({}, {"CARBON DIOXIDE": 1}),
    ({"PROPANE": 1}, {"PROPANE": 1}),
    ({"PROPANE": -1}, {"CARBON DIOXIDE": 1}),
])
def test_complex_reaction_rejected(api, react, prod):
    with pytest.raises(ValueError):
        api.reactions.add_complex_reaction(react, prod)
    assert not api.reactions.all()


def test_user_species_mass_balance_uses_their_mw(api):
    from pyfds.domain.model import Species
    for n, mw in (("A", 10.0), ("B", 20.0), ("C", 30.0)):
        api.species.add(Species(name=n, mw=mw))
    api.reactions.add_complex_reaction({"A": 1, "B": 1}, {"C": 1})
    with pytest.raises(ValueError):
        api.reactions.add_complex_reaction({"A": 1}, {"C": 1})


def test_imported_unbalanced_reaction_loads_and_is_warned(api, tmp_path):
    f = tmp_path / "c.fds"
    f.write_text("&HEAD CHID='c'/\n&REAC ID='R', SPEC_ID_NU='PROPANE','OXYGEN','CARBON DIOXIDE', NU=-1,-1,3 /\n&TAIL /\n")
    proj = FdsParser().parse(str(f))
    assert proj.reactions[0].nu == [-1, -1, 3]
    api2 = FdsApi(proj)
    assert any(r.rule == "ComplexReaction" for r in api2.validation.validate().results)


# -- HVC-01 ----------------------------------------------------------------------------------
def test_aircoil_round_trip_and_validation(api, tmp_path):
    api.hvac_nodes.add_node([0, 0, 0], name="N1")
    api.hvac_nodes.add_node([1, 0, 0], name="N2")
    api.hvac_ducts.add_duct("N1", "N2", name="D1")
    c = api.hvac_aircoils.add_aircoil("D1", 0.7, coolant_temperature=7.0, coolant_mass_flow=0.3, name="COIL")
    text, back = _roundtrip(api, tmp_path)
    assert "&HVAC TYPE_ID='AIRCOIL'" in text
    b = back.hvac_aircoils[0]
    assert (b.name, b.duct_id, b.effectiveness, b.coolant_temperature, b.coolant_mass_flow) == ("COIL", "D1", 0.7, 7.0, 0.3)
    with pytest.raises(KeyError):
        api.hvac_aircoils.add_aircoil("NOPE")
    with pytest.raises(ValueError):
        api.hvac_aircoils.add_aircoil("D1", 1.5)
    api.history.undo()
    assert api.hvac_aircoils.get("COIL") is None


# -- SIM-03 ----------------------------------------------------------------------------------
def test_gravity_ramps_round_trip(api, tmp_path):
    api.ramps.add_ramp("TILT", [0, 10], [0, 1])
    api.environment.set_gravity([0, 0, -9.81], ramp_x="TILT")
    assert api.environment.get()["gravity_ramps"] == ("TILT", None, None)
    text, back = _roundtrip(api, tmp_path)
    assert "RAMP_GX='TILT'" in text
    assert back.misc.ramp_gx == "TILT" and back.misc.ramp_gy is None
    api.environment.set_gravity(ramp_x=None)
    assert api.environment.get()["gravity_ramps"] == (None, None, None)


def test_gravity_and_ambient_validation_and_undo(api):
    with pytest.raises(KeyError):
        api.environment.set_gravity(ramp_z="NOPE")
    with pytest.raises(ValueError):
        api.environment.set_gravity([1, 2])
    with pytest.raises(ValueError):
        api.environment.set_ambient(humidity=150)
    with pytest.raises(ValueError):
        api.environment.set_ambient(pressure=5)
    before = api.environment.get()
    api.environment.set_ambient(temperature=30.0, pressure=100000.0, humidity=60.0)
    assert api.environment.get()["temperature"] == 30.0
    api.history.undo()
    assert api.environment.get() == before


def test_agent_tools(api):
    d = AgentToolDispatcher(api)
    assert d.call("add_typed_surface", {"kind": "burner", "heat_release_rate": 300.0, "name": "B"}) == "B"
    assert d.call("surface_kind", {"surface": "B"}) == "burner"
    assert d.call("add_liquid_fuel", {"name": "L", "fuel_species": "METHANOL", "boiling_temperature": 65.0,
                                      "heat_of_vaporization": 1100.0, "density": 790.0, "specific_heat": 2.5}) == "L"
    assert d.call("add_complex_reaction", {"reactants": {"PROPANE": 1, "OXYGEN": 5},
                                           "products": {"CARBON DIOXIDE": 3, "WATER VAPOR": 4}, "name": "R"}) == "R"
    d.call("set_ambient_conditions", {"temperature": 25.0})
    assert d.call("get_environment", {})["temperature"] == 25.0
    api.ramps.add_ramp("G", [0, 1], [0, 1])
    d.call("set_gravity", {"ramp_y": "G"})
    assert api.environment.get()["gravity_ramps"][1] == "G"
    d.call("set_gravity", {"ramp_y": ""})
    assert api.environment.get()["gravity_ramps"][1] is None
    api.hvac_nodes.add_node([0, 0, 0], name="N1")
    api.hvac_nodes.add_node([1, 0, 0], name="N2")
    api.hvac_ducts.add_duct("N1", "N2", name="D1")
    assert d.call("add_hvac_aircoil", {"duct_id": "D1", "name": "AC"})["name"] == "AC"
