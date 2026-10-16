"""F5: api.sim - the global parameter blocks (&TIME, &DUMP, &MISC, &PRES, &RADI)."""
import pytest

from pyfds.api import FdsApi


@pytest.fixture
def api():
    return FdsApi()


def test_blocks_and_values(api):
    assert [b["namelist"] for b in api.sim.blocks()] == ["TIME", "DUMP", "MISC", "PRES", "RADI"]
    assert api.sim.values("time")["t_end"] == 60.0 and "fds_extra" not in api.sim.values("time")
    assert api.sim.get("environment") is api.project.misc
    with pytest.raises(KeyError):
        api.sim.get("weather")


def test_update_is_one_undo_step_and_only_changes_what_differs(api):
    api.sim.update("time", t_end=300.0, t_begin=10.0, restrict_time_step=False)
    assert (api.project.params.t_end, api.project.params.t_begin) == (300.0, 10.0)
    api.history.undo()
    assert api.project.params.t_end == 60.0 and api.project.params.t_begin == 0.0 and api.project.params.restrict_time_step
    before = len(api.history.undo_stack) if hasattr(api.history, "undo_stack") else None
    api.sim.update("time", t_end=60.0)                       # nothing differs: no step is recorded
    if before is not None:
        assert len(api.history.undo_stack) == before


def test_invalid_values_are_refused_and_nothing_changes(api):
    for block, bad in (("time", {"t_end": -5.0}), ("time", {"t_end": 5.0, "t_begin": 9.0}), ("time", {"dt": 0.0}),
                       ("environment", {"humidity": 140.0}), ("environment", {"tmpa": 500.0}),
                       ("output", {"dt_slcf": -1.0}), ("environment", {"p_inf": 0.0}),
                       ("time", {"t_end": "soon"}), ("time", {"nonsense": 1})):
        with pytest.raises(ValueError):
            api.sim.update(block, **bad)
    assert api.project.params.t_end == 60.0 and api.project.misc.humidity == 40.0


def test_check_reports_without_changing(api):
    assert api.sim.check("time", t_end=100.0) == []
    assert "T_END must be later than T_BEGIN" in api.sim.check("time", t_end=1.0, t_begin=2.0)
    assert api.project.params.t_end == 60.0


def test_reset_restores_defaults(api):
    api.sim.update("environment", tmpa=35.0, humidity=80.0, gvec=(0.0, 0.0, -1.62))
    api.sim.reset("environment")
    assert api.project.misc.tmpa == 20.0 and api.project.misc.gvec == (0.0, 0.0, -9.81)


def test_extras_set_remove_and_table(api):
    api.sim.set_extra("environment", "tmpa_extra_like", "1")
    assert api.sim.extras("environment") == {"TMPA_EXTRA_LIKE": "1"}
    with pytest.raises(ValueError):
        api.sim.set_extra("environment", "TMPA", "25")              # typed field: use update
    with pytest.raises(ValueError):
        api.sim.set_extra("environment", "bad key", "1")
    api.sim.set_extras("environment", {"ALPHA": "2", "BETA": ".TRUE."})
    assert api.sim.extras("environment") == {"ALPHA": "2", "BETA": ".TRUE."}
    api.history.undo()
    assert api.sim.extras("environment") == {"TMPA_EXTRA_LIKE": "1"}
    api.sim.remove_extra("environment", "tmpa_extra_like")
    assert api.sim.extras("environment") == {}
    with pytest.raises(KeyError):
        api.sim.remove_extra("environment", "NOPE")


def test_changes_reach_the_fds_text(api):
    api.sim.update("time", t_end=123.0)
    api.sim.update("output", dt_slcf=0.5)
    api.sim.set_extra("environment", "SOME_KEY", "7")
    text = api.fds_text()
    assert "T_END=123" in text and "DT_SLCF=0.5" in text and "SOME_KEY=7" in text
