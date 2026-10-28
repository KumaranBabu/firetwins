"""F5: the Simulation Parameters dialog (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.editors.sim_params import SimulationParametersDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    return FdsApi()


@pytest.fixture
def dlg(api, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[-1]))
    d = SimulationParametersDialog(api)
    d.warned = warned
    yield d
    d.close()


def test_one_tab_per_block_with_every_typed_field(dlg, api):
    assert [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())] == ["Time", "Output", "Environment", "Pressure", "Radiation"]
    assert dlg.field_widget("environment", "tmpa").value() == 20.0
    assert dlg.field_widget("environment", "gvec").value() == (0.0, 0.0, -9.81)
    assert dlg.field_widget("environment", "turbulence_model").value() == "DEARDORFF"
    assert "DYNAMIC SMAGORINSKY" in [dlg.field_widget("environment", "turbulence_model").widget.itemText(i)
                                     for i in range(dlg.field_widget("environment", "turbulence_model").widget.count())]
    assert dlg.field_widget("time", "dt").value() is None            # optional, empty
    assert not dlg.is_dirty()


def test_apply_saves_every_tab_as_one_undo_step(dlg, api):
    dlg.field_widget("time", "t_end").set_value(500.0)
    dlg.field_widget("output", "dt_slcf").set_value(0.25)
    dlg.field_widget("environment", "humidity").set_value(60.0)
    dlg.field_widget("radiation", "number_radiation_angles").set_value(200)
    assert dlg.is_dirty()
    done = dlg.apply()
    assert set(done) == {"time", "output", "environment", "radiation"}
    assert (api.project.params.t_end, api.project.dump.dt_slcf, api.project.misc.humidity,
            api.project.radi.number_radiation_angles) == (500.0, 0.25, 60.0, 200)
    api.history.undo()
    assert (api.project.params.t_end, api.project.dump.dt_slcf, api.project.misc.humidity) == (60.0, 1.0, 40.0)
    assert api.project.radi.number_radiation_angles == 104          # FDS's own default


def test_invalid_input_changes_nothing_and_says_which_tab(dlg, api):
    dlg.field_widget("time", "t_end").set_value(400.0)               # fine on its own ...
    dlg.field_widget("environment", "humidity").set_value(150.0)      # ... but this one is not
    with pytest.raises(ValueError, match="Environment: HUMIDITY"):
        dlg.apply()
    assert api.project.params.t_end == 60.0                            # nothing was saved, not even the good tab
    assert not dlg._apply_quietly() and "HUMIDITY" in dlg.warned[-1]
    dlg.field_widget("time", "t_end").set_value(0.0)                   # earlier than the start time
    dlg.field_widget("environment", "humidity").set_value(50.0)
    with pytest.raises(ValueError, match="T_END"):
        dlg.apply()


def test_units_follow_the_project(api):
    api.units.set_system("EN")
    d = SimulationParametersDialog(api)
    assert d.field_widget("environment", "tmpa").value() == pytest.approx(68.0)          # 20 C shown in F
    d.field_widget("environment", "tmpa").set_value(86.0)
    d.apply()
    assert api.project.misc.tmpa == pytest.approx(30.0)
    assert d.field_widget("environment", "p_inf").value() == pytest.approx(api.units.to_display(101325.0, "pressure"))
    d.close()


def test_additional_keywords_table(dlg, api):
    dlg._add_row(dlg._tables["environment"], "my_key", "3")
    dlg._add_row(dlg._tables["time"], "", "ignored")                  # a blank keyword is ignored
    assert dlg.extras_in_table("environment") == {"MY_KEY": "3"} and dlg.is_dirty()
    dlg.apply()
    assert api.sim.extras("environment") == {"MY_KEY": "3"} and api.sim.extras("time") == {}
    dlg._tables["environment"].selectRow(0)
    dlg._remove_rows(dlg._tables["environment"])
    dlg.apply()
    assert api.sim.extras("environment") == {}
    dlg._add_row(dlg._tables["environment"], "TMPA", "5")             # a typed field cannot be an extra
    with pytest.raises(ValueError):
        dlg.apply()


def test_reset_to_defaults_is_unsaved_until_apply(dlg, api):
    api.sim.update("environment", tmpa=33.0)
    d = SimulationParametersDialog(api)
    d.reset_block("environment")
    assert d.field_widget("environment", "tmpa").value() == 20.0 and api.project.misc.tmpa == 33.0
    d.apply()
    assert api.project.misc.tmpa == 20.0
    d.close()


def test_ok_closes_only_when_valid(dlg, api):
    dlg.field_widget("time", "t_end").set_value(-1.0)
    dlg._on_ok()
    assert dlg.result() == 0 and dlg.warned
    dlg.field_widget("time", "t_end").set_value(90.0)
    dlg._on_ok()
    assert dlg.result() == 1 and api.project.params.t_end == 90.0
