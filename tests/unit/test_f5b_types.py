"""F5 (type-specific parts): surface types choose the tabs; materials get a Byproducts tab and a pyrolysis calculator."""
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pyfds.api import FdsApi
from pyfds.gui.editors import layouts, material_calc
from pyfds.gui.editors.model import EntityEditorModel


@pytest.fixture
def api():
    return FdsApi()


def _specs(api, attr):
    m = EntityEditorModel(api, attr)
    return m.fields(m.create())


# -- layouts (no Qt) -----------------------------------------------------------------------------------
def test_every_surface_type_has_a_layout_and_nothing_is_lost(api):
    specs = _specs(api, "surfaces")
    names = {s.name for s in specs}
    for kind in api.surfaces.kinds():
        lay = layouts.surface_layout(kind, specs)
        placed = [n for tab in lay.tabs.values() for n in tab]
        assert sorted(placed) == sorted(names), kind                    # each field on exactly one tab
        assert lay.tabs["General"][0] == "name" and not lay.hidden


def test_type_specific_tabs(api):
    specs = _specs(api, "surfaces")
    burner = layouts.surface_layout("burner", specs).tabs
    assert burner["Heat Release"] == ["heat_release_rate", "tau_q", "ramp_q"] and "Particle Injection" in burner
    assert "layers" in burner["Advanced"] and "vel" in burner["Advanced"]
    assert layouts.surface_layout("supply", specs).tabs["Flow"][:3] == ["vel", "volume_flow", "mass_flux"]
    assert "Layers" in layouts.surface_layout("layered", specs).tabs and "Heat Release" not in layouts.surface_layout("layered", specs).tabs
    assert layouts.surface_layout("air_leak", specs).tabs["Leak"] == ["leak_path"]
    assert {"Heat Release", "Flow", "Layers", "Leak"} <= set(layouts.surface_layout("general", specs).tabs)
    with pytest.raises(ValueError):
        layouts.surface_layout("magic", specs)
    assert layouts.layout_for("meshes", specs) is None


def test_material_layout_hides_the_byproduct_fields(api):
    lay = layouts.material_layout(_specs(api, "materials"))
    assert list(lay.tabs)[:4] == ["General", "Thermal Properties", "Pyrolysis", "Reactions"]
    assert lay.hidden == {"nu_residue", "nu_gases", "spec_ids"} and "nu_gases" not in lay.tabs.get("Advanced", [])
    assert "heating_rate" in lay.tabs["Pyrolysis"] or "heating_rate" in lay.tabs["Advanced"]


# -- the calculator (no Qt) -------------------------------------------------------------------------------
def _arrhenius(temps, a, e):
    return [a * math.exp(-e / (8.314462618 * (t + 273.15))) for t in temps]


def test_match_rate_curve_leaves_a_and_e_to_fds(api):
    mat = api.materials.create_default("W")
    r = material_calc.compute(api, mat, "match", {"reference_temperature": 350, "heating_rate": 10, "pyrolysis_range": 80})
    assert r.values == {"a": None, "e": None, "n_s": 1.0, "reference_temperature": 350.0, "heating_rate": 10.0,
                        "pyrolysis_range": 80.0}
    with pytest.raises(ValueError, match="give"):
        material_calc.compute(api, mat, "match", {"reference_temperature": 350})
    with pytest.raises(ValueError, match="positive"):
        material_calc.compute(api, mat, "match", {"reference_temperature": 350, "heating_rate": 0, "pyrolysis_range": 80})


def test_direct_fit_and_peak(api):
    mat = api.materials.create_default("W")
    assert material_calc.compute(api, mat, "direct", {"a": 1e10, "e": 1.5e5}).values["e"] == 1.5e5
    with pytest.raises(ValueError):
        material_calc.compute(api, mat, "direct", {"a": -1, "e": 1})
    temps = list(range(250, 400, 10))
    fit = material_calc.compute(api, mat, "fit", {"temperatures": temps, "rates": _arrhenius(temps, 1e8, 100e3)})
    assert fit.values["e"] == pytest.approx(100e3, rel=1e-6) and "R2" in fit.note
    with pytest.raises(ValueError, match="same number"):
        material_calc.compute(api, mat, "fit", {"temperatures": [1, 2], "rates": [1]})
    peak = material_calc.compute(api, mat, "peak", {"heating_rate": 10, "peak_temperature": 350, "e": 100e3})
    assert peak.values["a"] > 0
    two = material_calc.compute(api, mat, "peak", {"heating_rate": 10, "peak_temperature": 350, "other_runs": [[20, 365]]})
    assert two.values["e"] > 0
    with pytest.raises(ValueError):
        material_calc.compute(api, mat, "peak", {"heating_rate": 10, "peak_temperature": 350})
    assert api.materials.get("W").a is None                                    # nothing was applied
    with pytest.raises(ValueError):
        material_calc.compute(api, mat, "nope", {})
    assert material_calc.parse_pairs("420 0.001\n430, 0.002;440\t0.004") == [[420, 0.001], [430, 0.002], [440, 0.004]]
    with pytest.raises(ValueError):
        material_calc.parse_pairs("a b")


# -- the dialog ------------------------------------------------------------------------------------------------
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from pyfds.gui.editors.collection_editor import EntityCollectionEditor  # noqa: E402
from pyfds.gui.editors.material_widgets import PyrolysisCalculatorDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


def _tabs(ed):
    return [ed.tabs.tabText(i) for i in range(ed.tabs.count())]


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)


def test_surface_type_selector_changes_tabs_and_keeps_values(api, quiet):
    ed = EntityCollectionEditor(api, "surfaces", "Edit Surfaces")
    s = ed.new_object()
    assert ed.type_combo.currentData() == "basic" and "Heat Release" not in _tabs(ed)
    ed._on_type_chosen(ed.type_combo.findData("burner"))
    assert _tabs(ed)[:3] == ["General", "Heat Release", "Thermal"] and _tabs(ed)[-1] == "Advanced"
    ed.field_widget("heat_release_rate").set_value(1000.0)
    ed._on_type_chosen(ed.type_combo.findData("supply"))
    assert "Flow" in _tabs(ed) and "Heat Release" not in _tabs(ed)
    assert ed.field_widget("heat_release_rate").value() == 1000.0          # typed values survive a change of type
    ed.apply()
    assert s.heat_release_rate == 1000.0
    ed.close()


def test_an_existing_surface_opens_on_its_own_type_and_the_pick_resets(api, quiet):
    api.surfaces.add_typed("burner", "FIRE", heat_release_rate=500.0)
    api.surfaces.create_default("PLAIN")
    ed = EntityCollectionEditor(api, "surfaces", "Edit Surfaces", select="FIRE")
    assert ed.type_combo.currentData() == "burner" and "Heat Release" in _tabs(ed)
    ed.select("PLAIN")
    assert ed.type_combo.currentData() == "basic"
    ed._on_type_chosen(ed.type_combo.findData("layered"))
    ed.select("FIRE")
    assert ed.type_combo.currentData() == "burner"                          # the pick belongs to one object
    ed.close()


def test_live_type_note_names_the_type_and_the_contradictions(api, quiet):
    ed = EntityCollectionEditor(api, "surfaces", "Edit Surfaces")
    ed.new_object()
    ed._on_type_chosen(ed.type_combo.findData("general"))
    assert "basic" in ed.type_note.text()
    ed.field_widget("heat_release_rate").set_value(800.0)
    assert "burner" in ed.type_note.text() and "!" not in ed.type_note.text()
    ed.field_widget("tmp_front").set_value(100.0)
    assert "general" in ed.type_note.text() and "both a heat release rate and a fixed temperature" in ed.type_note.text()
    ed.close()


def test_the_type_selector_is_only_for_surfaces(api):
    ed = EntityCollectionEditor(api, "meshes", "Edit Meshes")
    assert ed.type_row.isHidden() and ed.type_note.isHidden()
    ed.close()


def test_material_tabs_and_byproducts_round_trip(api, quiet):
    api.materials.create_default("CHAR")
    ed = EntityCollectionEditor(api, "materials", "Edit Materials", select="CHAR")
    mat = ed.new_object()
    assert _tabs(ed) == ["General", "Thermal Properties", "Pyrolysis", "Reactions", "Byproducts", "Advanced"]
    bw = ed._byproducts
    bw.add_gas("PROPANE", 0.6)
    bw.add_gas("CARBON MONOXIDE", 0.1)
    bw.residue_yield.setText("0.2")
    bw.residue_material.setCurrentText("CHAR")
    assert "unaccounted 0.100" in bw.total.text()
    assert "NU_MATL=0.2" in ed.preview_text() and "NU_SPEC=0.6,0.1" in ed.preview_text()
    ed.apply()
    assert (mat.spec_ids, mat.nu_gases, mat.nu_residue, mat.residue_id) == (["PROPANE", "CARBON MONOXIDE"], [0.6, 0.1], 0.2, "CHAR")
    assert api.materials.byproducts(mat.name)["residue_material"] == "CHAR"
    ed.select("CHAR")
    ed.select(mat.name)
    assert ed._byproducts.gases() == {"species": ["PROPANE", "CARBON MONOXIDE"], "yields": [0.6, 0.1]}
    api.history.undo()
    assert mat.spec_ids is None and mat.residue_id is None
    ed.close()


def test_byproduct_mistakes_are_refused(api, quiet):
    api.materials.create_default("CHAR")
    ed = EntityCollectionEditor(api, "materials", "Edit Materials", select="CHAR")
    mat = ed.new_object()
    bw = ed._byproducts
    bw.add_gas("PROPANE", 0.9)
    bw.residue_yield.setText("0.3")
    bw.residue_material.setCurrentText("CHAR")
    with pytest.raises(ValueError, match="cannot exceed 1"):
        ed.apply()
    bw.residue_yield.setText("0.05")
    bw.residue_material.setCurrentText("")
    with pytest.raises(ValueError, match="residue material"):
        ed.apply()
    bw.residue_material.setCurrentText(mat.name)
    with pytest.raises(ValueError, match="own residue"):
        ed.apply()
    bw.residue_material.setCurrentText("NOPE")
    with pytest.raises(ValueError, match="does not exist"):
        ed.apply()
    bw.table.setItem(0, 1, type(bw.table.item(0, 1))("abc"))
    with pytest.raises(ValueError, match="not a number"):
        ed.apply()
    assert mat.spec_ids is None
    ed.close()


def _run_calculator(ed, monkeypatch, method_index, fill, target=0):
    def fake_exec(self):
        self.target.setCurrentIndex(target)
        self.method.setCurrentIndex(method_index)
        fill(self)
        return QDialog.Accepted if self.result() is not None else QDialog.Rejected
    monkeypatch.setattr(PyrolysisCalculatorDialog, "exec", fake_exec)
    return ed.open_pyrolysis_calculator()


def test_calculator_match_rate_curve_fills_the_main_reaction(api, quiet, monkeypatch):
    ed = EntityCollectionEditor(api, "materials", "Edit Materials")
    mat = ed.new_object()

    def fill(dlg):
        dlg.edits["0:reference_temperature"].setText("350")
        dlg.edits["0:heating_rate"].setText("10")
        dlg.edits["0:pyrolysis_range"].setText("80")
    got = _run_calculator(ed, monkeypatch, 0, fill)
    assert got["reference_temperature"] == 350.0 and ed.field_widget("heating_rate").value() == 10.0
    assert mat.reference_temperature is None                               # unsaved until Apply
    ed.apply()
    assert (mat.reference_temperature, mat.heating_rate, mat.pyrolysis_range, mat.a) == (350.0, 10.0, 80.0, None)
    assert "HEATING_RATE=10" in ed.preview_text()
    ed.close()


def test_calculator_direct_and_cancelled_and_invalid(api, quiet, monkeypatch):
    ed = EntityCollectionEditor(api, "materials", "Edit Materials")
    mat = ed.new_object()
    got = _run_calculator(ed, monkeypatch, 3, lambda d: (d.edits["direct_a"].setText("1e10"), d.edits["direct_e"].setText("1.5e5")))
    assert got["a"] == 1e10 and ed.field_widget("e").value() == 1.5e5
    assert _run_calculator(ed, monkeypatch, 3, lambda d: None) is None          # nothing typed: cannot accept
    ed.apply()
    assert (mat.a, mat.e) == (1e10, 1.5e5)
    ed.close()


def test_calculator_fit_and_peak_through_the_dialog(api, quiet, monkeypatch):
    ed = EntityCollectionEditor(api, "materials", "Edit Materials")
    mat = ed.new_object()
    temps = list(range(250, 400, 10))
    rows = "\n".join(f"{t} {r}" for t, r in zip(temps, _arrhenius(temps, 1e8, 100e3)))
    got = _run_calculator(ed, monkeypatch, 1, lambda d: d.texts["fit"].setPlainText(rows))
    assert got["e"] == pytest.approx(100e3, rel=1e-6)
    def peak(d):
        d.edits["2:heating_rate"].setText("10")
        d.edits["2:peak_temperature"].setText("350")
        d.edits["2:e"].setText("100000")
    got = _run_calculator(ed, monkeypatch, 2, peak)
    assert got["a"] > 0 and ed.field_widget("e").value() == 100000.0
    ed.close()


def test_calculator_on_a_step_of_a_multi_step_material(api, quiet, monkeypatch):
    ed = EntityCollectionEditor(api, "materials", "Edit Materials")
    mat = ed.new_object()
    ed.field_widget("reactions").add_row({"heat_of_reaction": 300.0})
    ed.field_widget("reactions").add_row({"heat_of_reaction": 500.0})
    got = _run_calculator(ed, monkeypatch, 3, lambda d: (d.edits["direct_a"].setText("2e9"), d.edits["direct_e"].setText("9e4")), target=1)
    assert got == {"a": 2e9, "e": 9e4, "n_s": 1.0}
    rows = ed.field_widget("reactions").value()
    assert rows[0]["a"] is None and rows[1]["a"] == 2e9 and rows[1]["heat_of_reaction"] == 500.0
    ed.apply()
    assert mat.reactions[1].a == 2e9 and mat.reactions[0].a is None
    # matching a rate curve does not apply to a step: it says so and changes nothing
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    assert ed.apply_calculation({"a": None}, 0, "match") is None and "main reaction" in shown[0]
    ed.close()
