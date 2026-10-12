"""
Unit tests — Phase 2/3 public exports and CLI additions.

Covers:
  - All Phase 2/3 types importable from top-level pyfds
  - pyfds info <file.q>   — prints Plot3D header metadata
  - pyfds info <file.prt5> — prints particle class metadata
  - pyfds report <dir>    — writes text/HTML report to file
"""
from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import List

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Binary helpers (minimal valid files)
# ---------------------------------------------------------------------------

def _fr(data: bytes) -> bytes:
    n = struct.pack("<i", len(data))
    return n + data + n


def _str30(s: str) -> bytes:
    return s.encode("ascii").ljust(30)[:30]


def _str_record(s: str) -> bytes:
    return _fr(_str30(s))


def _str_block_record(strings: List[str]) -> bytes:
    return _fr(b"".join(_str30(s) for s in strings))


def _make_plot3d(path: Path) -> None:
    buf = io.BytesIO()
    buf.write(_fr(struct.pack("<i", 2)))
    buf.write(_str_block_record(["TEMPERATURE", "PRESSURE"]))
    buf.write(_str_block_record(["C", "Pa"]))
    buf.write(_fr(struct.pack("<3i", 4, 3, 2)))
    for t in [0.0, 5.0]:
        buf.write(_fr(struct.pack("<f", t)))
        buf.write(_fr(np.zeros(2 * 4 * 3 * 2, dtype=np.float32).tobytes()))
    path.write_bytes(buf.getvalue())


def _make_prt5(path: Path) -> None:
    buf = io.BytesIO()
    buf.write(_str_record("mycase"))
    buf.write(_fr(struct.pack("<i", 1)))
    buf.write(_str_record("DROPLETS"))
    buf.write(_fr(struct.pack("<i", 1)))
    buf.write(_str_block_record(["DIAMETER"]))
    buf.write(_str_block_record(["m"]))
    buf.write(_fr(struct.pack("<f", 0.0) + struct.pack("<i", 2)))
    for arr in [
        np.array([0.0, 0.1], dtype=np.float32),
        np.array([0.0, 0.1], dtype=np.float32),
        np.array([0.5, 0.5], dtype=np.float32),
    ]:
        buf.write(_fr(arr.tobytes()))
    buf.write(_fr(np.array([1, 2], dtype=np.int32).tobytes()))
    buf.write(_fr(np.full(2, 0.001, dtype=np.float32).tobytes()))
    path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# TestPublicExports
# ---------------------------------------------------------------------------

class TestPublicExports:
    """All Phase 2/3 names must be importable from the top-level pyfds package."""

    def test_plot3d_reader(self):
        from pyfds import Plot3DReader
        assert Plot3DReader is not None

    def test_plot3d_result(self):
        from pyfds import Plot3DResult
        assert Plot3DResult is not None

    def test_particle_reader(self):
        from pyfds import ParticleReader
        assert ParticleReader is not None

    def test_particle_result(self):
        from pyfds import ParticleResult
        assert ParticleResult is not None

    def test_particle_class(self):
        from pyfds import ParticleClass
        assert ParticleClass is not None

    def test_particle_frame(self):
        from pyfds import ParticleFrame
        assert ParticleFrame is not None

    def test_simulation_report(self):
        from pyfds import SimulationReport
        assert SimulationReport is not None

    def test_report_section(self):
        from pyfds import ReportSection
        assert ReportSection is not None

    def test_simulation_stats(self):
        from pyfds import SimulationStats
        assert SimulationStats is not None

    def test_plot_device_timeseries(self):
        from pyfds import plot_device_timeseries
        assert callable(plot_device_timeseries)

    def test_plot_hrr(self):
        from pyfds import plot_hrr
        assert callable(plot_hrr)

    def test_plot_slice_contour(self):
        from pyfds import plot_slice_contour
        assert callable(plot_slice_contour)

    def test_plot_multi_quantity(self):
        from pyfds import plot_multi_quantity
        assert callable(plot_multi_quantity)

    def test_plot_particle_positions(self):
        from pyfds import plot_particle_positions
        assert callable(plot_particle_positions)

    def test_all_names_in_dunder_all(self):
        import pyfds
        for name in [
            "Plot3DReader", "Plot3DResult",
            "ParticleReader", "ParticleResult", "ParticleClass", "ParticleFrame",
            "SimulationReport", "ReportSection", "SimulationStats",
            "plot_device_timeseries", "plot_hrr", "plot_slice_contour",
            "plot_multi_quantity", "plot_particle_positions",
        ]:
            assert name in pyfds.__all__, f"{name!r} missing from pyfds.__all__"


# ---------------------------------------------------------------------------
# TestCliInfo — .q and .prt5 extensions
# ---------------------------------------------------------------------------

class TestCliInfoExtensions:

    def test_info_plot3d_prints_metadata(self, tmp_path, capsys):
        from pyfds.cli.main import cmd_info
        import argparse
        q = tmp_path / "case_01.q"
        _make_plot3d(q)
        args = argparse.Namespace(path=str(q))
        rc = cmd_info(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Plot3D" in out
        assert "TEMPERATURE" in out
        assert "PRESSURE" in out
        assert "Frames" in out

    def test_info_plot3d_shows_shape(self, tmp_path, capsys):
        from pyfds.cli.main import cmd_info
        import argparse
        q = tmp_path / "case_01.q"
        _make_plot3d(q)
        args = argparse.Namespace(path=str(q))
        cmd_info(args)
        out = capsys.readouterr().out
        assert "4" in out and "3" in out and "2" in out

    def test_info_plot3d_shows_time_range(self, tmp_path, capsys):
        from pyfds.cli.main import cmd_info
        import argparse
        q = tmp_path / "case_01.q"
        _make_plot3d(q)
        args = argparse.Namespace(path=str(q))
        cmd_info(args)
        out = capsys.readouterr().out
        assert "0.00" in out and "5.00" in out

    def test_info_prt5_prints_metadata(self, tmp_path, capsys):
        from pyfds.cli.main import cmd_info
        import argparse
        prt = tmp_path / "case_01.prt5"
        _make_prt5(prt)
        args = argparse.Namespace(path=str(prt))
        rc = cmd_info(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Particle" in out
        assert "DROPLETS" in out
        assert "mycase" in out

    def test_info_prt5_shows_quantity_names(self, tmp_path, capsys):
        from pyfds.cli.main import cmd_info
        import argparse
        prt = tmp_path / "case_01.prt5"
        _make_prt5(prt)
        args = argparse.Namespace(path=str(prt))
        cmd_info(args)
        out = capsys.readouterr().out
        assert "DIAMETER" in out

    def test_info_unknown_extension_returns_error(self, tmp_path):
        from pyfds.cli.main import cmd_info
        import argparse
        f = tmp_path / "data.xyz"
        f.write_text("nothing")
        args = argparse.Namespace(path=str(f))
        rc = cmd_info(args)
        assert rc == 1


# ---------------------------------------------------------------------------
# TestCliReport
# ---------------------------------------------------------------------------

class TestCliReport:

    def test_report_text_creates_file(self, tmp_path):
        from pyfds.cli.main import cmd_report
        import argparse
        out_file = tmp_path / "report.txt"
        args = argparse.Namespace(
            output_dir=str(tmp_path),
            output=str(out_file),
            fmt="text",
            title=None,
        )
        rc = cmd_report(args)
        assert rc == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_report_html_creates_file(self, tmp_path):
        from pyfds.cli.main import cmd_report
        import argparse
        out_file = tmp_path / "report.html"
        args = argparse.Namespace(
            output_dir=str(tmp_path),
            output=str(out_file),
            fmt="html",
            title="Test Report",
        )
        rc = cmd_report(args)
        assert rc == 0
        content = out_file.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Test Report" in content

    def test_report_uses_custom_title(self, tmp_path):
        from pyfds.cli.main import cmd_report
        import argparse
        out_file = tmp_path / "r.txt"
        args = argparse.Namespace(
            output_dir=str(tmp_path),
            output=str(out_file),
            fmt="text",
            title="My Custom Title",
        )
        cmd_report(args)
        content = out_file.read_text(encoding="utf-8")
        assert "My Custom Title" in content

    def test_report_default_output_path(self, tmp_path):
        from pyfds.cli.main import cmd_report
        import argparse
        args = argparse.Namespace(
            output_dir=str(tmp_path),
            output=None,
            fmt="text",
            title=None,
        )
        rc = cmd_report(args)
        assert rc == 0
        txt_files = list(tmp_path.glob("*_report.txt"))
        assert len(txt_files) == 1

    def test_report_nonexistent_dir_returns_error(self, tmp_path):
        from pyfds.cli.main import cmd_report
        import argparse
        args = argparse.Namespace(
            output_dir=str(tmp_path / "no_such_dir"),
            output=None,
            fmt="text",
            title=None,
        )
        rc = cmd_report(args)
        assert rc == 1

    def test_report_subcommand_registered_in_parser(self):
        from pyfds.cli.main import build_parser
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["report", "--help"])
        assert exc_info.value.code == 0

    def test_main_report_end_to_end(self, tmp_path):
        from pyfds.cli.main import main
        out_file = tmp_path / "out.txt"
        rc = main(["report", str(tmp_path), "-o", str(out_file)])
        assert rc == 0
        assert out_file.exists()
