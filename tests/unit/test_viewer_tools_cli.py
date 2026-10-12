"""Agent tools and the scripted command line for the results viewer."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyfds.agent.registry import get_tool
from pyfds.api.facade import FdsApi
from pyfds.gui.results import cli

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
R = "root/FDS Results/"


@pytest.fixture()
def run(tmp_path):
    d = tmp_path / "run"
    shutil.copytree(FIX, d)
    return d


def call(api, tool, **kw):
    return get_tool(tool).handler(api, **kw)


def test_agent_tools_drive_the_viewer(run):
    api = FdsApi()
    s = call(api, "viewer_open", source=str(run / "rroom.smv"))
    assert s["results"] == "rroom"
    ids = [n["id"] for n in call(api, "viewer_list", kind="slice2d")]
    assert ids
    s = call(api, "viewer_show", node=ids[0], on=True)
    assert ids[0] in s["active"]
    call(api, "viewer_seek", time=3.0)
    assert 2.5 <= api.viewer.time <= 3.5
    bar = call(api, "viewer_colorbar", quantity="TEMPERATURE")
    assert bar["max"] > bar["min"]
    call(api, "viewer_colorbar", quantity="TEMPERATURE", minimum=0.0, maximum=200.0)
    assert api.viewer.colorbar("TEMPERATURE").hi == 200.0
    assert call(api, "viewer_view", name="top")["position"][2] > 0
    with pytest.raises(RuntimeError):
        call(api, "viewer_screenshot", path=str(run / "x.png"))          # nothing attached to draw
    out = call(api, "viewer_save")
    assert out.endswith(".pyfdsv") and Path(out).exists()


def test_cli_screenshot_and_errors(run, capsys):
    shot = run / "cli.png"
    assert cli.main(["-screenshot", "-ssname", str(shot), "-sswidth", "240", "-ssheight", "160", "-sstime", "2", str(run / "rroom.smv")]) == 0
    assert shot.stat().st_size > 500
    assert cli.main(["-screenshot", str(run / "missing.smv")]) == 1
    assert cli.main(["-bogus", "x"]) == 1
    assert cli.main([str(run / "rroom.smv")]) == 1
    err = capsys.readouterr().err
    assert "not found" in err and "unknown option" in err and "choose -screenshot or -movie" in err
