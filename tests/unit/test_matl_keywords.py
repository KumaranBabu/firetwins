"""MATL output that FDS 6.10.1 accepts: NU_SPEC for the gases of every material, NU_MATL + MATL_ID for a residue,
HEATING_RATE for matching a rate curve; and the model check that a residue yield needs a residue material."""
import pytest

from pyfds.api import FdsApi
from pyfds.domain.model import Material, MaterialReaction
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter


def _matl_line(api, name):
    return next(l for l in FdsWriter().to_string(api.project).splitlines() if l.startswith(f"&MATL ID='{name}'"))


def _api():
    a = FdsApi()
    a.materials.add(Material(name="CHAR"))
    return a


def test_gases_are_always_nu_spec_and_residue_is_a_material():
    a = _api()
    a.materials.add(Material(name="WOOD", spec_ids=["PROPANE"], nu_gases=[0.7], nu_residue=0.2, residue_id="CHAR",
                             reference_temperature=350.0, heating_rate=10.0, pyrolysis_range=80.0))
    line = _matl_line(a, "WOOD")
    assert "NU_SPEC=0.7" in line and "NU_MATL=0.2" in line and "MATL_ID='CHAR'" in line
    assert "NU_GASES" not in line and "NU_RESIDUE" not in line and "HEATING_RATE=10.0" in line


def test_a_residue_yield_without_a_residue_material_is_not_written():
    a = _api()
    a.materials.add(Material(name="WOOD", nu_residue=0.2))
    assert "NU_MATL" not in _matl_line(a, "WOOD") and "MATL_ID" not in _matl_line(a, "WOOD")


def test_round_trip_and_old_files_still_read():
    a = _api()
    a.materials.add(Material(name="WOOD", spec_ids=["PROPANE"], nu_gases=[0.7], nu_residue=0.2, residue_id="CHAR",
                             heating_rate=10.0, pyrolysis_range=80.0, reference_rate=0.01))
    back = FdsParser().parse_string(FdsWriter().to_string(a.project))
    w = next(m for m in back.materials if m.name == "WOOD")
    assert (w.nu_gases, w.nu_residue, w.residue_id, w.heating_rate, w.pyrolysis_range, w.reference_rate) == (
        [0.7], 0.2, "CHAR", 10.0, 80.0, 0.01)
    old = FdsParser().parse_string("&MATL ID='OLD', NU_GASES=0.4, SPEC_ID='X', NU_RESIDUE=0.1 /\n&TAIL /").materials[0]
    assert old.nu_gases == [0.4] and old.nu_residue == 0.1 and old.residue_id is None


def test_per_reaction_orders_are_written_when_every_step_has_one():
    a = FdsApi()
    a.materials.add(Material(name="M", reactions=[MaterialReaction(a=1e9, e=9e4, n_s=1.0),
                                                  MaterialReaction(a=2e9, e=8e4, n_s=2.0)]))
    assert "N_S=1.0,2.0" in _matl_line(a, "M")
    b = FdsApi()
    b.materials.add(Material(name="M", reactions=[MaterialReaction(a=1e9, e=9e4, n_s=1.0), MaterialReaction(a=2e9, e=8e4)]))
    assert "N_S" not in _matl_line(b, "M")


def test_residue_rule():
    a = _api()
    a.materials.add(Material(name="WOOD", nu_residue=0.2))
    found = [r for r in a.validation.validate().results if r.rule == "MaterialResidue"]
    assert len(found) == 1 and found[0].severity.name == "WARNING" and "not written" in found[0].message
    a.materials.update("WOOD", residue_id="NOPE")
    assert any("not defined" in r.message for r in a.validation.validate().results if r.rule == "MaterialResidue")
    a.materials.update("WOOD", residue_id="CHAR", nu_gases=[0.9], spec_ids=["X"])
    assert any("more than 1" in r.message for r in a.validation.validate().results if r.rule == "MaterialResidue")
    a.materials.update("WOOD", nu_gases=[0.5])
    assert not [r for r in a.validation.validate().results if r.rule == "MaterialResidue"]


def test_surface_problems_api():
    a = FdsApi()
    s = a.surfaces.add_typed("burner", "FIRE", heat_release_rate=100.0)
    assert a.surfaces.problems(s) == [] and a.surfaces.problems("FIRE") == []
    a.surfaces.update(s, tmp_front=50.0)
    assert "both a heat release rate and a fixed temperature" in a.surfaces.problems(s)[0]
    assert set(a.surfaces.kinds()) >= {"burner", "supply", "layered"}
    with pytest.raises(KeyError):
        a.surfaces.problems("NOPE")
