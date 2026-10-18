"""
Shared pytest fixtures for the PyFDS test suite.
"""
from __future__ import annotations

import io
import os
import struct
import sys
from pathlib import Path
from typing import Generator

import pytest

# Force the headless Agg backend before any test imports matplotlib.pyplot.
# Since PySide6 was added (for src/pyfds/gui), matplotlib auto-selects the
# interactive "qtagg" backend by default; constructing interactive widgets
# (Slider/SpanSelector, used by plot_timeseries_interactive/animate_slice)
# under qtagg outside a running Qt event loop crashes the process natively,
# and does so early enough in collection/import order that it can leave
# matplotlib's global backend state broken for the rest of the session.
# Setting this once, here, before any test module runs, makes the backend
# deterministic regardless of what else gets installed later.
import matplotlib
matplotlib.use("Agg", force=True)

# Ensure the package is importable from the tests directory.
SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Project / EventBus fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_event_bus():
    """Reset the global EventBus before every test to prevent cross-test pollution."""
    from pyfds.core.events import reset_global_bus
    reset_global_bus()
    yield
    reset_global_bus()


@pytest.fixture(autouse=True)
def no_real_qsettings(monkeypatch):
    """GUI tests must never touch the real OS settings store: main_window's
    Recent Projects list lives under HKCU\\Software\\PyFDS\\PyFDS on Windows
    (via QSettings("PyFDS", "PyFDS")) — the exact same key the live desktop
    app writes to. Without this, running the suite silently pollutes a real
    user's Recent Projects with test tmp_path entries (confirmed happening:
    `reg query HKCU\\Software\\PyFDS\\PyFDS` showed several
    .pytest_tmp/.../case.fds paths from test_save_as_writes_fds_file runs
    mixed in with the user's actual saved project)."""
    try:
        from tests.mw_proxy import main_window_mod as mw
    except ImportError:
        yield
        return

    class _FakeQSettings:
        _store: dict = {}

        def __init__(self, org, app):
            self._key = (org, app)
            self._store.setdefault(self._key, {})

        def value(self, key, default=None):
            return self._store[self._key].get(key, default)

        def setValue(self, key, value):
            self._store[self._key][key] = value

    monkeypatch.setattr(mw, "QSettings", _FakeQSettings)
    yield


@pytest.fixture
def blank_project():
    """Return a minimal FdsProject with one mesh (using real model fields)."""
    from pyfds.domain.model import FdsProject, Mesh
    p = FdsProject()
    p.chid = "test_project"
    p.add_entity(Mesh(name="m1", cell_count=(10, 10, 5),
                      x_min=0, x_max=2, y_min=0, y_max=2, z_min=0, z_max=1))
    return p


@pytest.fixture
def room_fire_project():
    """Return a small but complete room-fire project (real model fields)."""
    from pyfds.domain.model import (
        FdsProject, Mesh, Obstruction, Surface, Vent, Device, Ramp,
        SimulationParams,
    )
    p = FdsProject()
    p.chid = "room_fire"
    p.title = "Room Fire"
    p.params = SimulationParams(t_end=60.0)

    p.add_entity(Mesh(name="mesh_01", cell_count=(20, 20, 10),
                      x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=2))
    p.add_entity(Surface(name="fire", heat_release_rate=500.0, tau_q=-1.0))
    p.add_entity(Surface(name="inert_wall"))
    p.add_entity(Obstruction(name="floor",
                             x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=0.1,
                             surface_id="inert_wall"))
    p.add_entity(Obstruction(name="burner",
                             x_min=1.5, x_max=2.5, y_min=1.5, y_max=2.5, z_min=0.1, z_max=0.2,
                             surface_id="fire"))
    p.add_entity(Vent(name="ceiling_open",
                      x_min=0, x_max=4, y_min=0, y_max=4, z_min=2, z_max=2,
                      surface_id="OPEN"))
    p.add_entity(Device(name="tc_center", quantity="TEMPERATURE", xyz=(2.0, 2.0, 1.5)))
    p.add_entity(Ramp(name="tau_fire", times=[0.0, 30.0, 60.0], values=[0.0, 1.0, 1.0]))
    return p


@pytest.fixture
def simple_room_fds_path():
    """Return path to the simple_room.fds fixture file."""
    return str(FIXTURES_DIR / "simple_room.fds")


@pytest.fixture
def multi_mesh_fds_path():
    """Return path to the multi_mesh.fds fixture file."""
    return str(FIXTURES_DIR / "multi_mesh.fds")


# ---------------------------------------------------------------------------
# Binary fixture builders (Fortran unformatted records)
# ---------------------------------------------------------------------------

def _fortran_record(data: bytes) -> bytes:
    """Wrap data in Fortran unformatted record (leading + trailing int32 length)."""
    length = struct.pack("<i", len(data))
    return length + data + length


def _fortran_string(s: str) -> bytes:
    """Encode a string as a Fortran record (30-char padded, as FDS writes it)."""
    padded = s.encode("ascii").ljust(30)[:30]
    return _fortran_record(padded)


@pytest.fixture
def fake_slice_file(tmp_path):
    """
    Build a minimal valid .sf (slice) binary file in FDS format.
    Header: 3 string records (quantity, short_name, units)
    Index record: i1, i2, j1, j2, k1, k2  (6 × int32)
    Frames: time (float32) + data array (float32 × ni×nj×nk)
    """
    ni, nj = 3, 3
    i1, i2, j1, j2, k1, k2 = 0, ni - 1, 0, nj - 1, 5, 5  # planar in z

    buf = io.BytesIO()
    buf.write(_fortran_string("TEMPERATURE"))
    buf.write(_fortran_string("temp"))
    buf.write(_fortran_string("C"))
    # index record
    idx_data = struct.pack("<6i", i1, i2, j1, j2, k1, k2)
    buf.write(_fortran_record(idx_data))

    # two frames
    n_values = (i2 - i1 + 1) * (j2 - j1 + 1) * (k2 - k1 + 1)
    for t in [0.0, 1.0]:
        time_data = struct.pack("<f", t)
        buf.write(_fortran_record(time_data))
        vals = struct.pack(f"<{n_values}f", *[float(t * 100 + i) for i in range(n_values)])
        buf.write(_fortran_record(vals))

    path = tmp_path / "test_01.sf"
    path.write_bytes(buf.getvalue())
    return str(path)


@pytest.fixture
def fake_devc_csv(tmp_path):
    """Create a minimal _devc.csv file."""
    content = (
        "Time,tc_center,tc_ceiling,hrr_total\n"
        "s,C,C,kW\n"
        "0.0,20.0,20.0,0.0\n"
        "1.0,21.5,20.5,10.0\n"
        "2.0,24.0,21.0,50.0\n"
        "3.0,30.0,22.0,200.0\n"
    )
    path = tmp_path / "room_fire_devc.csv"
    path.write_text(content)
    return str(path)


@pytest.fixture
def fake_out_file(tmp_path):
    """Create a minimal FDS .out file."""
    content = """\
 FDS Version: 6.9.1
 CHID: room_fire
 T_END=   60.000
 Simulation completed successfully.
 Total wall clock time: 12.34 s
"""
    path = tmp_path / "room_fire.out"
    path.write_text(content)
    return str(path)


@pytest.fixture(autouse=True)
def _isolated_user_config(tmp_path_factory, monkeypatch):
    """Tests never read or write the real user_data/config.json."""
    import pyfds.core.config as cfg_mod
    folder = tmp_path_factory.mktemp("userconf")
    monkeypatch.setattr(cfg_mod, "_CONFIG_DIR", folder)
    monkeypatch.setattr(cfg_mod, "_CONFIG_FILE", folder / "config.json")
