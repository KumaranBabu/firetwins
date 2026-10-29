"""FDS writer: only parameters the user set are written (&PRES), arithmetic noise is not written, old projects migrate."""
from __future__ import annotations

import json

from pyfds.domain.model import FdsProject
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.fds_writer_common import _fmt
from pyfds.io.serializer import Serializer


def _pres_lines(project) -> list:
    return [line for line in FdsWriter().to_string(project).splitlines() if line.startswith("&PRES")]


def test_default_project_writes_no_pres_record():
    assert _pres_lines(FdsProject()) == []


def test_pres_writes_only_what_was_set():
    p = FdsProject()
    p.pres.velocity_tolerance = 0.01
    p.pres.max_pressure_iterations = 50
    p.pres.solver = "uglmat"
    (line,) = _pres_lines(p)
    assert "VELOCITY_TOLERANCE=0.01" in line and "MAX_PRESSURE_ITERATIONS=50" in line and "SOLVER='UGLMAT'" in line


def test_pres_round_trip_keeps_solver_and_extras(tmp_path):
    src = tmp_path / "in.fds"
    src.write_text("&HEAD CHID='t' /\n&PRES SOLVER='UGLMAT', CHECK_POISSON=.TRUE. /\n&TAIL /\n")
    p = FdsParser().parse(str(src))
    assert p.pres.solver == "UGLMAT" and p.pres.velocity_tolerance is None
    (line,) = _pres_lines(p)
    assert "SOLVER='UGLMAT'" in line and "CHECK_POISSON" in line and "VELOCITY_TOLERANCE" not in line


def test_old_project_defaults_are_migrated():
    data = json.loads(Serializer().save_string(FdsProject()))
    data["pres"].update(velocity_tolerance=0.05, max_pressure_iterations=10, mach_number_limit=0.3,
                        pressure_iterations=1, solver="SCARC")          # what a project saved before the fix held
    p = Serializer().load_string(json.dumps(data))
    assert p.pres.velocity_tolerance is None and p.pres.solver == "FFT"
    assert _pres_lines(p) == []


def test_arithmetic_noise_is_not_written_but_real_digits_are():
    assert _fmt(0.65 * 3) == "1.95"
    assert _fmt(0.1 + 0.2) == "0.3"
    assert _fmt(1.2345678901234567) == "1.2345678901234567"
