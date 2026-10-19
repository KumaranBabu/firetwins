"""Keywords the writer used to emit that real FDS 6.10 rejects with ERROR 101 (found by checking the writer against the FDS User Guide
and the bundled FDS)."""
from __future__ import annotations

from pyfds.domain.model import FdsProject, Geom, Init, Mesh, Move, Particle, Reaction, Surface, Zone
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter


def _text(project) -> str:
    return FdsWriter().generate_content(project)


def _line(text: str, name: str) -> str:
    return next(l for l in text.splitlines() if l.startswith(f"&{name}"))


def test_zone_leak_areas_are_indexed(tmp_path):
    p = FdsProject()
    p.add_entity(Zone(name="Z1", xyz=(0.5, 0.5, 0.5), leak_areas=[0.001, 0.0, 0.002]))
    line = _line(_text(p), "ZONE")
    assert "LEAK_AREA(0)=0.001" in line and "LEAK_AREA(2)=0.002" in line and "LEAK_AREAS" not in line
    f = tmp_path / "z.fds"
    f.write_text(_text(p), encoding="utf-8")
    assert FdsParser().parse(str(f)).zones[0].leak_areas == [0.001, 0.0, 0.002]


def test_old_leak_areas_file_still_reads(tmp_path):
    f = tmp_path / "old.fds"
    f.write_text("&HEAD CHID='o' /\n&ZONE ID='Z', XYZ=0.5,0.5,0.5, LEAK_AREAS=0.1,0.2 /\n&TAIL /\n", encoding="utf-8")
    assert FdsParser().parse(str(f)).zones[0].leak_areas == [0.1, 0.2]


def test_surface_ignition_temperature_keyword(tmp_path):
    p = FdsProject()
    p.add_entity(Surface(name="S", ignition_temperature=300.0))
    line = _line(_text(p), "SURF")
    assert "IGNITION_TEMPERATURE=300" in line and "AUTO_IGNITION" not in line
    f = tmp_path / "s.fds"
    f.write_text(_text(p), encoding="utf-8")
    assert FdsParser().parse(str(f)).surfaces[0].ignition_temperature == 300.0


def test_initial_wind_goes_to_wind_line(tmp_path):
    p = FdsProject()
    p.misc.u0, p.misc.v0 = 1.5, -2.0
    text = _text(p)
    assert "U0" not in _line(text, "MISC") and "U0=1.5" in _line(text, "WIND")
    f = tmp_path / "w.fds"
    f.write_text(text, encoding="utf-8")
    back = FdsParser().parse(str(f))
    assert (back.misc.u0, back.misc.v0) == (1.5, -2.0) and back.wind_profiles == []


def test_invalid_keywords_are_not_written():
    p = FdsProject()
    p.misc.openmp_threads = 4
    p.add_entity(Move(name="M", omega=2.0, velocity=(0.0, 0.0, 1.0)))
    p.add_entity(Init(name="I", temperature=30.0, density=1.2))
    p.add_entity(Particle(name="P", sigma=0.1)) if "sigma" in Particle.model_fields else None
    p.add_entity(Reaction(name="R", fuel="PROPANE", soot_h_fraction=0.1))
    text = _text(p)
    for key in ("OPENMP_THREADS", "OMEGA", "VELOCITY=", "SOOT_H_FRACTION", "SIGMA"):
        assert key not in text, key
    assert "DENSITY" not in _line(text, "INIT")


def test_options_the_editor_offers_reach_the_fds_file(tmp_path):
    """These model fields (and their dialog rows) used to be dropped when the .fds was written."""
    p = FdsProject()
    p.params.restrict_time_step = False
    p.dump.write_xyz, p.dump.render_file = True, "case.ge1"
    p.radi.time_step_increment = 2
    p.add_entity(Reaction(name="R", fuel="PROPANE", lower_oxygen_limit=0.12, critical_flame_temperature=1300.0,
                          auto_ignition_temperature=300.0))
    text = _text(p)
    assert "RESTRICT_TIME_STEP=.FALSE." in _line(text, "TIME")
    assert "WRITE_XYZ=.TRUE." in _line(text, "DUMP") and "RENDER_FILE='case.ge1'" in _line(text, "DUMP")
    assert "TIME_STEP_INCREMENT=2" in _line(text, "RADI")
    reac = _line(text, "REAC")
    assert "LOWER_OXYGEN_LIMIT=0.12" in reac and "CRITICAL_FLAME_TEMPERATURE=1300" in reac and "AUTO_IGNITION_TEMPERATURE=300" in reac
    f = tmp_path / "o.fds"
    f.write_text(text, encoding="utf-8")
    back = FdsParser().parse(str(f))
    assert back.params.restrict_time_step is False and back.dump.write_xyz is True and back.dump.render_file == "case.ge1"
    assert back.radi.time_step_increment == 2
    r = back.reactions[0]
    assert (r.lower_oxygen_limit, r.critical_flame_temperature, r.auto_ignition_temperature) == (0.12, 1300.0, 300.0)


def test_defaults_are_not_written():
    text = _text(FdsProject())
    for key in ("RESTRICT_TIME_STEP", "WRITE_XYZ", "RENDER_FILE", "TIME_STEP_INCREMENT"):
        assert key not in text
