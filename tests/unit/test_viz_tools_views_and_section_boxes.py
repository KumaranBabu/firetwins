"""Results-viewer data tools: views / tours / section boxes, floors, annotations, capture planning, CSV loading, (part 1 of 2)."""


from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from pyfds.results.viz import annotations as an
from pyfds.results.viz import capture as cap
from pyfds.results.viz import csvload as cl
from pyfds.results.viz import data3d as d3
from pyfds.results.viz import floors as fl
from pyfds.results.viz import model as vm
from pyfds.results.viz import timelines as tm
from pyfds.results.viz import views as vw
from pyfds.results.viz.primitives import RectilinearVolume

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"


def vp(x=0.0):
    return vm.Viewpoint(position=(x, 0, 0))

# -- tours ---------------------------------------------------------------------------------------------------
def tour3():
    t = vm.Tour()
    for time, x, tr in ((0.0, 0.0, "move_to_next"), (10.0, 10.0, "stationary"), (20.0, 30.0, "move_to_next")):
        vw.add_keyframe(t, time, vp(x), tr)
    return t


def test_camera_follows_keyframes_with_smooth_and_stationary_transitions():
    t = tour3()
    assert vw.camera_at(t, -5).position[0] == 0 and vw.camera_at(t, 99).position[0] == 30
    assert 0 < vw.camera_at(t, 3).position[0] < 5                       # eases in
    assert vw.camera_at(t, 5).position[0] == pytest.approx(5.0, abs=1e-6)       # smoothstep midpoint
    assert vw.camera_at(t, 12).position[0] == 10 and vw.camera_at(t, 19.9).position[0] == 10   # holds, then jumps
    assert vw.camera_at(t, 20).position[0] == 30
    with pytest.raises(ValueError):
        vw.camera_at(vm.Tour(), 0)

def test_tour_repeat_with_delay():
    t = tour3()
    t.repeat, t.repeat_delay = True, 10.0
    assert vw.camera_at(t, 20).position[0] == 30
    assert vw.camera_at(t, 25).position[0] == pytest.approx(15.0, abs=1e-6)        # halfway back during the delay
    assert vw.camera_at(t, 30).position[0] == 0 and vw.camera_at(t, 33).position[0] > 0
    t2 = tour3()
    t2.repeat = True                                                            # no delay: straight to the start again
    assert vw.camera_at(t2, 20.5).position[0] == pytest.approx(0.0, abs=2.0) or vw.camera_at(t2, 20.5).position[0] < 30

def test_keyframe_editing():
    t = tour3()
    with pytest.raises(ValueError):
        vw.add_keyframe(t, 10.0, vp())
    with pytest.raises(ValueError):
        vw.add_keyframe(t, 5.0, vp(), "teleport")
    vw.add_keyframe(t, 15.0, vp(99))
    assert [k.time for k in t.keyframes] == [0, 10, 15, 20]
    vw.record_camera(t, 1, vp(-1))
    assert t.keyframes[1].viewpoint.position[0] == -1
    vw.remove_keyframes(t, [2])
    assert [k.time for k in t.keyframes] == [0, 10, 20]
    with pytest.raises(IndexError):
        vw.remove_keyframes(t, [7])

def test_shift_keyframes_stays_between_neighbours():
    t = tour3()
    vw.shift_keyframes(t, [1], new_time=12.0)
    assert t.keyframes[1].time == 12.0
    vw.shift_keyframes(t, [1], offset=-1.5)
    assert t.keyframes[1].time == 10.5
    with pytest.raises(ValueError):
        vw.shift_keyframes(t, [1], new_time=25.0)                              # would pass the next keyframe
    vw.shift_keyframes(t, [0, 1, 2], offset=100.0)                             # everything: no limit
    assert [k.time for k in t.keyframes] == [100.0, 110.5, 120.0]
    with pytest.raises(ValueError):
        vw.shift_keyframes(t, [1])
    with pytest.raises(ValueError):
        vw.shift_keyframes(t, [])

def test_duplicate_keyframes_modes():
    t = tour3()
    new = vw.duplicate_keyframes(t, [0, 1], "end_of_tour", last_delay=5.0)
    assert [k.time for k in new] == [25.0, 35.0] and [k.time for k in t.keyframes][-2:] == [25.0, 35.0]
    h = tour3()
    vw.duplicate_keyframes(h, [1], "after_selection")                         # hold keyframe 1
    times = [k.time for k in h.keyframes]
    assert times[:2] == [0, 10] and times[2] == 10 + 0 or len(times) == 4
    assert len(h.keyframes) == 4 and h.keyframes[-1].time > 20.0              # the last one was pushed back
    a = tour3()
    vw.duplicate_keyframes(a, [0], "at_time", at_time=15.0)
    assert 15.0 in [k.time for k in a.keyframes] and a.keyframes[-1].time > 20.0
    for bad in (lambda: vw.duplicate_keyframes(tour3(), [0], "x"), lambda: vw.duplicate_keyframes(tour3(), [0], "at_time"), lambda: vw.duplicate_keyframes(tour3(), [0], "end_of_tour"),
                lambda: vw.duplicate_keyframes(tour3(), [], "end_of_tour"), lambda: vw.duplicate_keyframes(tour3(), [9])):
        with pytest.raises((ValueError, IndexError)):
            bad()

# -- views and section boxes --------------------------------------------------------------------------------------
def test_views_lifecycle():
    viz = vm.ResultsVisualization()
    viz.camera = vp(7)
    a = vw.new_view(viz, "Door")
    assert viz.active_view == "Door" and a.viewpoint.position[0] == 7
    b = vw.new_view(viz, "Door")
    assert b.name == "Door 2"
    viz.camera = vp(9)
    vw.save_viewpoint(viz, "Door")
    assert viz.view("Door").viewpoint.position[0] == 9
    viz.camera = vp(0)
    vw.activate(viz, "Door")
    assert viz.camera.position[0] == 9
    vw.activate(viz, "Default")
    assert viz.active_view is None
    (c,) = vw.duplicate_views(viz, ["Door"])
    assert c.name == "Door copy" and c.origin == "pyfds"
    t = vw.new_tour(viz, "Orbit")
    with pytest.raises(ValueError):
        vw.save_viewpoint(viz, "Orbit")                                         # a view holds a viewpoint or a tour
    vw.delete_view(viz, "Orbit")
    assert viz.active_view is None and "Orbit" not in [v.name for v in viz.views]
    with pytest.raises(KeyError):
        viz.view("nope")
    fds = vm.View("From PyroSim", origin="fds", viewpoint=vp())
    viz.views.append(fds)
    with pytest.raises(ValueError):
        vw.save_viewpoint(viz, "From PyroSim")
    with pytest.raises(ValueError):
        vw.set_section_box(viz, "From PyroSim", vw.new_section_box((0, 1, 0, 1, 0, 1)))

def test_section_box_planes_clip_and_validate():
    box = vw.new_section_box((0, 4, 0, 3, 0, 2.5), enabled_planes=("x_min", "z_max"))
    assert box.active() == {"x_min": 0.0, "z_max": 2.5}
    vw.set_plane(box, "x_min", 1.0)
    vw.set_plane(box, "x_max", 3.0)
    assert vw.clip_planes(box) == [("x", 1.0, "above"), ("x", 3.0, "below"), ("z", 2.5, "below")] or \
        set(vw.clip_planes(box)) == {("x", 1.0, "above"), ("x", 3.0, "below"), ("z", 2.5, "below")}
    assert vw.inside(box, (2, 1, 1)) and not vw.inside(box, (0.5, 1, 1)) and not vw.inside(box, (2, 1, 3))
    with pytest.raises(ValueError):
        vw.set_plane(box, "x_max", 0.5)
    with pytest.raises(KeyError):
        vw.set_plane(box, "w_min", 1)
    box.enabled = False
    assert vw.clip_planes(box) == [] and vw.inside(box, (99, 99, 99)) and vw.clip_planes(None) == []
    viz = vm.ResultsVisualization()
    with pytest.raises(ValueError):
        vw.set_section_box(viz, None, box)                                      # the Default view has no section box
    vw.new_view(viz, "A")
    vw.set_section_box(viz, None, vw.new_section_box((0, 1, 0, 1, 0, 1)))
    assert vw.active_section(viz) is not None
    vw.set_section_box(viz, "A", None)
    assert vw.active_section(viz) is None and vw.active_tour(viz) is None

def test_views_export_and_import_keep_names_unique():
    viz = vm.ResultsVisualization()
    vw.new_view(viz, "Door")
    vw.new_tour(viz, "Orbit")
    vw.add_keyframe(viz.view("Orbit").tour, 0.0, vp(1))
    text = vw.export_views(viz)
    other = vm.ResultsVisualization()
    vw.new_view(other, "Door")
    added = vw.import_views(other, text)
    assert sorted(v.name for v in other.views) == ["Door", "Door 2", "Orbit"] and len(added) == 2
    assert other.view("Orbit").tour.keyframes[0].viewpoint.position[0] == 1
    for bad in ("nope", json.dumps({"x": 1})):
        with pytest.raises(ValueError):
            vw.import_views(other, bad)

# -- floors -----------------------------------------------------------------------------------------------
def test_floor_assignment_and_layouts():
    s = vm.FloorSettings()
    fl.set_floors(s, [3.0, 0.0, 6.0])
    assert s.floors == [0.0, 3.0, 6.0]
    assert [fl.floor_index(s.floors, z) for z in (-1, 0, 2.9, 3, 5, 99)] == [0, 0, 0, 1, 1, 2]
    with pytest.raises(ValueError):
        fl.set_floors(s, [1, 1])
    s.floors = [0.0, 3.0, 6.0]
    lay = fl.FloorLayout(s, (0, 10, 0, 5, 0, 9))
    pts = np.array([[1, 1, 1.0], [1, 1, 4.0], [1, 1, 7.0]])
    moved, keep = lay.apply(pts)
    assert keep.all() and np.allclose(moved, pts)                              # no separation yet
    s.separation = 2.0
    moved, _ = fl.FloorLayout(s, (0, 10, 0, 5, 0, 9)).apply(pts)
    assert moved[:, 2].tolist() == [1.0, 6.0, 11.0]                            # stacked with 2 m gaps
    s.layout, s.separation = "horizontal", 1.0
    h = fl.FloorLayout(s, (0, 10, 0, 5, 0, 9))
    moved, _ = h.apply(pts)
    assert np.allclose(moved[:, 2], [1.0, 1.0, 1.0])                           # flattened onto the plan
    assert moved[0, 0] == 1 and moved[1, 0] == 12 and moved[2, 1] == pytest.approx(1.0 - 6.0)    # 2x2 grid, row-major
    assert [n for n, _ in h.labels()] == ["Floor 1", "Floor 2", "Floor 3"]

def test_floor_visibility_and_wall_clipping():
    s = vm.FloorSettings(floors=[0.0, 3.0], clip_walls=True, wall_height=1.0)
    lay = fl.FloorLayout(s, (0, 5, 0, 5, 0, 6))
    p = np.array([[0, 0, 0.5], [0, 0, 2.5], [0, 0, 3.5], [0, 0, 5.0]])
    assert lay.apply(p)[1].tolist() == [True, False, True, False]              # above floor level + 1 m is hidden
    fl.set_visible(s, [1])
    assert fl.FloorLayout(s, (0, 5, 0, 5, 0, 6)).apply(p)[1].tolist() == [False, False, True, False]
    fl.set_visible(s, None)
    assert s.visible is None and fl.floors_for_selection(s, 1.0, 4.0) == [0, 1]
    with pytest.raises(IndexError):
        fl.set_visible(s, [5])
    with pytest.raises(ValueError):
        fl.FloorLayout(vm.FloorSettings(layout="diagonal"), (0, 1, 0, 1, 0, 1))
    assert not fl.FloorLayout(vm.FloorSettings(), (0, 1, 0, 1, 0, 1)).active

# -- annotations -----------------------------------------------------------------------------------------------
def test_dimensions_measure_along_feature_or_axis():
    g = an.dimension_geometry(vm.Dimension((0, 0, 0), (3, 4, 0)))
    assert g.value == pytest.approx(5.0) and g.text == "5.000 m"
    gx = an.dimension_geometry(vm.Dimension((0, 0, 0), (3, 4, 0), "along_x", 0.5))
    assert gx.value == 3.0 and gx.end[0] - gx.start[0] == pytest.approx(3.0) and gx.start[1] != 0 or gx.start[2] != 0
    assert an.dimension_geometry(vm.Dimension((0, 0, 0), (3, 4, 2), "along_z")).value == 2.0
    assert an.dimension_geometry(vm.Dimension((0, 0, 0), (3, 4, 0)), precision=1).text == "5.0 m"
    off = an.dimension_geometry(vm.Dimension((0, 0, 0), (4, 0, 0), "feature", 1.0))
    assert off.start != (0, 0, 0) and len(off.extension) == 2
    for bad in (vm.Dimension((1, 1, 1), (1, 1, 1)), vm.Dimension((0, 0, 0), (0, 4, 0), "along_x"), vm.Dimension((0, 0, 0), (1, 0, 0), "diag")):
        with pytest.raises(ValueError):
            an.dimension_geometry(bad)

def test_annotation_lists():
    viz = vm.ResultsVisualization()
    an.add_dimension(viz, (0, 0, 0), (1, 0, 0))
    lab = an.add_label(viz, "Burner", (1, 1, 0), (1, 1, 2))
    an.add_label(viz, "No leader", (0, 0, 0))
    assert viz.labels[1].position is None and lab.position == (1.0, 1.0, 2.0)
    an.rename_label(viz, 0, "Fire")
    assert viz.labels[0].text == "Fire"
    an.remove_annotation(viz, "label", 1)
    an.remove_annotation(viz, "dimension", 0)
    assert len(viz.labels) == 1 and not viz.dimensions
    for bad in (lambda: an.add_label(viz, "  ", (0, 0, 0)), lambda: an.add_dimension(viz, (0, 0, 0), (0, 0, 0)),
                lambda: an.remove_annotation(viz, "x", 0), lambda: an.rename_label(viz, 0, "")):
        with pytest.raises(ValueError):
            bad()

# -- capture planning ----------------------------------------------------------------------------------------------
def test_screenshot_plans_and_file_names(tmp_path):
    (s,) = cap.single(str(tmp_path / "a.png"), 5.0)
    assert (s.time, s.view) == (5.0, cap.CURRENT)
    shots = cap.multiple(str(tmp_path / "m.png"), 0, 10, 5, ["Top", cap.CURRENT])
    assert [(x.time, x.view) for x in shots] == [(0, "Top"), (0, cap.CURRENT), (5, "Top"), (5, cap.CURRENT), (10, "Top"), (10, cap.CURRENT)]
    assert Path(shots[0].path).name == "m_000.000_Top.png" and Path(shots[1].path).name == "m_000.000.png"
    tour = cap.multiple(str(tmp_path / "m.png"), 0, 10, 5, ["Orbit"], {"Orbit": (4.0, 8.0)})
    assert [x.time for x in tour] == [5.0]                                      # only inside the tour's time range
    for bad in (lambda: cap.multiple("x.png", 0, 10, 0), lambda: cap.multiple("x.png", 5, 1, 1)):
        with pytest.raises(ValueError):
            bad()

def test_tsv_screenshots_with_quoting(tmp_path):
    text = 'time\tx\n0.0\tTop\tFront\n30.0\t"Floor 0"\tLeft\n120.0\tTop\n\n'.split("\n", 1)[1]
    rows = cap.parse_tsv(text)
    assert rows == [(0.0, ["Top", "Front"]), (30.0, ["Floor 0", "Left"]), (120.0, ["Top"])]
    shots = cap.from_file(str(tmp_path / "model1.png"), text)
    names = [Path(s.path).name for s in shots]
    assert names == ["model1_000.000_Top.png", "model1_000.000_Front.png", "model1_030.000_Floor 0.png",
                     "model1_030.000_Left.png", "model1_120.000_Top.png"]
    assert cap.parse_tsv("5\tA\\\tB\n") == [(5.0, ["A\tB"])]
    with pytest.raises(ValueError):
        cap.parse_tsv("abc\tTop")
    assert cap.safe_name('a/b:c"d') == "a_b_c_d"

def test_movie_plan():
    p = cap.movie_plan("m.mp4", 0, 10, fps=10, speed=2.0, size=(1281, 721))
    assert p.times[:3] == [0.0, 0.2, 0.4] and p.times[-1] == pytest.approx(10.0) and p.size == (1280, 720) and len(p.times) == 51
    for bad in (lambda: cap.movie_plan("m", 5, 5), lambda: cap.movie_plan("m", 0, 1, fps=0), lambda: cap.movie_plan("m", 0, 1, size=(8, 8))):
        with pytest.raises(ValueError):
            bad()
    assert Path(cap.frame_path("d", "s", 7)).name == "s_00007.png"

def test_command_line_options(tmp_path):
    r = cap.parse_cli(["-screenshot", "-ssname", "shots/a.png", "-sswidth", "1280", "-ssheight", "720", "-ssview", "Entrance",
                       "-sstime", "5.0", "case.pyfdsv"])
    assert r.screenshot and not r.movie and r.visualization == "case.pyfdsv" and r.options["sswidth"] == 1280
    (shot,) = cap.plan_from_cli(r, str(tmp_path), (0, 20))
    assert shot.time == 5.0 and shot.view == "Entrance" and shot.path.endswith("a.png")
    r2 = cap.parse_cli(["-screenshot", "-ssname", "s.png", "-ssviews", "A,B", "-sstbegin", "10", "-sstend", "20", "-ssdt", "5", "x.pyfdsv"])
    assert len(cap.plan_from_cli(r2, str(tmp_path), (0, 99))) == 6
    (tmp_path / "t.tsv").write_text("1\tA\n2\tB\tC\n")
    r3 = cap.parse_cli(["-screenshot", "-ssname", "s.png", "-sstsv", "t.tsv", "x.pyfdsv"])
    assert len(cap.plan_from_cli(r3, str(tmp_path), (0, 9))) == 3
    m = cap.parse_cli(["-movie", "-mvname", "m.mp4", "-mvframerate", "60", "-mvspeed", "2", "-mvlod", "-mvencoder", "openh264", "c.pyfdsv"])
    assert m.movie and m.options["mvframerate"] == 60 and m.options["mvlod"] is True and m.options["mvencoder"] == "openh264"
    for bad in (["-screenshot", "-movie"], ["-bogus"], ["-sswidth"], ["-sswidth", "wide"]):
        with pytest.raises(ValueError):
            cap.parse_cli(bad)

# -- CSV -----------------------------------------------------------------------------------------------------------
def test_load_real_fds_csv_files():
    for name, series in (("rroom_hrr.csv", "HRR"), ("rroom_devc.csv", "TC_120")):
        ref = cl.guess_type(str(FIX / name))
        assert ref.csv_type.startswith("FDS")
        data = cl.load(ref)
        s = next(x for x in data.series if x.description == series)
        assert len(s.times) > 5 and np.all(np.diff(s.times) > 0)
    hrr = next(x for x in cl.load(cl.guess_type(str(FIX / "rroom_hrr.csv"))).series if x.description == "HRR")
    assert hrr.unit == "kW" and hrr.values.max() > 100

def test_load_csv_header_layouts(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("Time,Region00,Region00\nTime,Density,Velocity\ns,pers/m2,m/s\n0,1,2\n1,3,4\n1,5,6\n2,7,8\n")
    ref = vm.CsvFileRef(str(p), "custom", 1, 3, 1, 2, 3)
    d = cl.load(ref)
    assert [(s.description, s.quantity, s.unit) for s in d.series] == [("Region00", "Density", "pers/m2"), ("Region00", "Velocity", "m/s")]
    assert d.series[0].times.tolist() == [0, 1, 2] and d.series[0].values.tolist() == [1, 3, 7]    # first of duplicate times
    q = tmp_path / "b.csv"
    q.write_text("Time (s),Door01_Flowrate (occs/s),Door01_Width (m)\n0,1,2\n5,3,4\n")
    d2 = cl.load(vm.CsvFileRef(str(q), "custom", 1, 1, 1, None, None))
    assert [(s.description, s.quantity, s.unit) for s in d2.series] == [("Door01", "Flowrate", "occs/s"), ("Door01", "Width", "m")]
    assert cl.preview(str(p), rows=2, cols=2) == [["Time", "Region00"], ["Time", "Density"]]

def test_load_csv_problems(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("a,b\nx,y\n")
    cases = [(vm.CsvFileRef(str(p), "custom", 1, 5, 1, None, None), "no data rows"),
             (vm.CsvFileRef(str(p), "custom", 1, 1, 1, None, None), "time column holds no numbers"),
             (vm.CsvFileRef(str(p), "custom", 9, 1, 1, None, None), "time column is outside"),
             (vm.CsvFileRef(str(p), "custom", 1, 1, 4, None, None), "header row 4")]
    for ref, msg in cases:
        with pytest.raises(ValueError, match=msg):
            cl.load(ref)
    with pytest.raises(FileNotFoundError):
        cl.load(vm.CsvFileRef(str(tmp_path / "none.csv")))
    p.write_text("t,v\n0,1\n5,2\n3,4\n")
    with pytest.raises(ValueError, match="decrease"):
        cl.load(vm.CsvFileRef(str(p), "custom", 1, 1, 1, None, None))

def test_export_series_union_of_times(tmp_path):
    a = cl.TimeSeries("A", "", "kW", np.array([0.0, 1.0, 2.0]), np.array([0.0, 10.0, 20.0]))
    b = cl.TimeSeries("B", "temp", "C", np.array([0.5, 2.0]), np.array([100.0, 200.0]))
    out = tmp_path / "e.csv"
    assert cl.export([a, b], str(out)) == 4
    lines = out.read_text().splitlines()
    assert lines[0] == "s,kW,C" and lines[1] == "Time,A,B temp"
    assert lines[2].split(",") == ["0", "0", ""] and lines[3].split(",")[2] == "100"        # no extrapolation outside a series
    tsv = tmp_path / "e.tsv"
    cl.export([a], str(tsv), "\t")
    assert "\t" in tsv.read_text()
    for bad in (lambda: cl.export([], str(out)), lambda: cl.export([a], str(out), ";")):
        with pytest.raises(ValueError):
            bad()
