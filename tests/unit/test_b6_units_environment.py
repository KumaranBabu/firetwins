"""B6: unit system, Monin-Obukhov wind presets, global particle settings, WIND names FDS accepts."""
import pytest

from pyfds.api import FdsApi
from pyfds.domain import units as U
from pyfds.domain import wind_presets as W
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.serializer import Serializer


def _roundtrip(api):
    text = FdsWriter().to_string(api.project)
    return text, FdsParser().parse_string(text)


def test_unit_conversions():
    assert U.to_display(100, "temperature", "EN") == pytest.approx(212.0)
    assert U.from_display(212, "temperature", "EN") == pytest.approx(100.0)
    assert U.to_display(1.0, "length", "EN") == pytest.approx(3.28084, rel=1e-5)
    assert U.convert(10, "length", "EN", "SI") == pytest.approx(3.048)
    assert U.to_display(5, "temperature_delta", "EN") == pytest.approx(9.0)  # no offset for a difference
    assert U.label("heat_flux", "EN") == "Btu/s/ft2"
    with pytest.raises(KeyError):
        U.to_display(1, "bogus", "EN")
    with pytest.raises(ValueError):
        U.label("length", "furlong")


@pytest.mark.parametrize("kind", U.kinds())
def test_unit_round_trip_every_kind(kind):
    assert U.from_display(U.to_display(12.5, kind, "EN"), kind, "EN") == pytest.approx(12.5)


def test_api_units_persist_and_undo_free(tmp_path):
    api = FdsApi()
    assert api.units.system == "SI"
    api.units.set_system("english")
    assert api.units.system == "EN"
    assert api.units.to_display(20, "temperature") == pytest.approx(68.0)
    assert api.units.from_display(68, "temperature") == pytest.approx(20.0)
    path = tmp_path / "u.pyfds"
    Serializer().save(api.project, str(path))
    assert Serializer().load(str(path)).editor.units == "EN"
    with pytest.raises(ValueError):
        api.units.set_system("cubits")


def test_monin_obukhov_classes():
    assert W.obukhov_length("D", 0.03) is None
    unstable = W.obukhov_length("B", 0.03)
    stable = W.obukhov_length("F", 0.03)
    assert unstable < 0 < stable
    assert W.obukhov_length("A", 0.03) > unstable        
    with pytest.raises(KeyError):
        W.obukhov_length("Z", 0.1)
    with pytest.raises(KeyError):
        W.roughness_length("moon")


def test_wind_preset_is_undoable_and_written_with_fds_names():
    api = FdsApi()
    wind = api.wind.monin_obukhov(speed=4.0, direction=225, stability="F", landscape="open")
    assert wind.z0 == pytest.approx(0.03) and wind.l > 0
    text, parsed = _roundtrip(api)
    wind_line = next(l for l in text.splitlines() if l.startswith("&WIND"))
    assert "Z_0=" in wind_line.replace(" ", "") or "Z_0 =" in wind_line
    assert "Z0=" not in wind_line.replace(" ", "").replace("Z_0=", "")
    assert parsed.wind_profiles[0].z0 == pytest.approx(0.03)
    api.history.undo()
    assert len(api.project.wind_profiles) == 0
    with pytest.raises(ValueError):
        api.wind.monin_obukhov(speed=3, landscape="open", z0=0.1)


def test_wind_new_fields_round_trip():
    api = FdsApi()
    from pyfds.domain.model import WindProfile
    api.project.add_entity(WindProfile(name="w", speed=3, z0=0.1, ground_level=5, lapse_rate=-0.0098,
                                       stratification=True, theta_star=0.1, latitude=40))
    _, parsed = _roundtrip(api)
    w = parsed.wind_profiles[0]
    assert (w.ground_level, w.lapse_rate, w.stratification, w.theta_star) == (5, -0.0098, True, 0.1)


def test_particle_settings_round_trip_and_undo():
    api = FdsApi()
    api.environment.set_particle_settings(particle_cfl=True, particle_cfl_max=0.5, maximum_particles=500000)
    text, parsed = _roundtrip(api)
    assert "PARTICLE_CFL=.TRUE." in text.replace(" ", "")
    assert "MAXIMUM_PARTICLES=500000" in text.replace(" ", "")
    assert parsed.misc.particle_cfl is True and parsed.misc.particle_cfl_max == 0.5
    assert parsed.dump.maximum_particles == 500000
    api.history.undo()
    assert api.environment.particle_settings() == {"particle_cfl": False, "particle_cfl_max": None,
                                                   "maximum_particles": None}
    with pytest.raises(ValueError):
        api.environment.set_particle_settings(maximum_particles=0)


def test_agent_tools_registered():
    from pyfds.agent.registry import TOOL_REGISTRY
    names = {t.name for t in TOOL_REGISTRY}
    assert {"set_unit_system", "convert_units", "add_monin_obukhov_wind", "set_particle_settings"} <= names
