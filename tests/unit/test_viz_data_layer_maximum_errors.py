"""Results-viewer data layer against real FDS 6.10.1 output (tests/fixtures/results_room): SMV model, streaming (part 2 of 2)."""


from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import numpy as np
import pytest

from pyfds.results.viz import colorbar as cb
from pyfds.results.viz import max_errors as me
from pyfds.results.viz import model as vm
from pyfds.results.viz import streams as st
from pyfds.results.viz import units as un
from pyfds.results.viz.dataset import QuantityStats, ResultsDataset
from pyfds.results.viz.fds_run import parse_smv
from pyfds.results.viz.primitives import ErrorBoxes, GeometryBoxes, GridSurface, PointCloud, RectilinearVolume, TriMesh, VectorField
from pyfds.results.viz.tree import ActivationModel, build_tree

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"


@pytest.fixture(scope="module")
def run():
    return parse_smv(str(FIX / "rroom.smv"))

@pytest.fixture
def copy(tmp_path):
    d = tmp_path / "run"
    shutil.copytree(FIX, d)
    return d

# -- tree and activation -----------------------------------------------------------------------------------
@pytest.fixture
def tree(run):
    viz = vm.ResultsVisualization()
    return build_tree(run, viz), viz

# -- dataset ---------------------------------------------------------------------------------------------
@pytest.fixture
def ds(run, tree):
    root, viz = tree
    d = ResultsDataset(run, viz, use_cache=False)
    return d, root, viz

def _leaf(root, path):
    return root.find("root/FDS Results/" + path)


# -- maximum errors --------------------------------------------------------------------------------------
def test_max_errors_from_the_log(run):
    e = me.read_max_errors(str(FIX / "rroom.out"))
    assert len(e["VELOCITY"]) == len(e["PRESSURE"]) == 21
    first = e["VELOCITY"][0]
    assert (first.mesh, first.cell) == (1, (10, 9, 2)) and first.value == pytest.approx(0.0018)
    s = me.at_time(e["PRESSURE"], 100.0)
    assert s is e["PRESSURE"][-1] and me.at_time(e["PRESSURE"], -1.0) is e["PRESSURE"][0]
    box = me.cell_box(run.mesh(1), (10, 9, 2))
    assert box == pytest.approx((1.35, 1.5, 1.2, 1.35, 0.15, 0.3))
    assert me.read_max_errors(str(FIX / "none.out"))["VELOCITY"] == [] and me.at_time([], 1.0) is None

def test_dataset_timeline_and_offsets(ds):
    d, root, viz = ds
    leaves = [_leaf(root, "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1"), _leaf(root, "Particles/DROPS/Mesh 1")]
    tl = d.timeline(leaves)
    assert tl[0] == 0.0 and tl[-1] == pytest.approx(6.0) and len(tl) == 13
    viz.timelines.fds_offset = -2.0
    assert d.timeline(leaves)[0] == pytest.approx(-2.0)
    assert d.timeline([root.find("geometry/fds_actual")]).size == 0

def test_dataset_slice_surface_in_real_coordinates(ds):
    d, root, viz = ds
    leaf = _leaf(root, "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 2")
    (g,) = d.primitives(leaf, 6.0)
    assert isinstance(g, GridSurface) and g.axis == "y" and g.position == 1.5
    assert g.x.min() == pytest.approx(1.5) and g.x.max() == pytest.approx(3.0) and g.z.max() == pytest.approx(2.25)
    assert g.values.shape == g.x.shape and g.values.max() > 100

def test_dataset_interpolates_between_frames_when_asked(ds):
    d, root, viz = ds
    leaf = _leaf(root, "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    times = d.leaf_times(leaf)
    mid = float((times[5] + times[6]) / 2)
    v5, v6 = (d.primitives(leaf, float(times[k]))[0].values for k in (5, 6))
    viz.fds.interpolate = False
    assert np.allclose(d.primitives(leaf, mid)[0].values, v5)
    viz.fds.interpolate = True
    assert np.allclose(d.primitives(leaf, mid)[0].values, (v5 + v6) / 2, atol=1e-3)

def test_dataset_units_follow_preferences(ds):
    d, root, viz = ds
    leaf = _leaf(root, "2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    c = d.primitives(leaf, 6.0)[0]
    viz.units.temperature = "F"
    f = d.primitives(leaf, 6.0)[0]
    assert (c.units, f.units) == ("C", "F") and f.values.max() == pytest.approx(c.values.max() * 1.8 + 32, rel=1e-4)

def test_dataset_volumes_smoke_and_fire(ds):
    d, root, viz = ds
    (v,) = d.primitives(_leaf(root, "3D Slices/TEMPERATURE/T_3D/Mesh 1"), 6.0)
    assert isinstance(v, RectilinearVolume) and v.values.shape == (11, 21, 16) and v.values.max() > 300
    (fire,) = d.primitives(_leaf(root, "3D Smoke/HRRPUV/Mesh 1"), 6.0)
    assert fire.kind == "fire" and 0 < fire.values.max() <= 1200.0 and fire.x.shape == (11,)
    (smoke,) = d.primitives(_leaf(root, "3D Smoke/SOOT DENSITY/Mesh 1"), 6.0)
    assert smoke.kind == "smoke" and smoke.extinction.max() > 0 and smoke.extinction.shape == smoke.values.shape
    (p3,) = d.primitives(_leaf(root, "Plot3D/TEMPERATURE/Mesh 1"), 6.0)
    assert p3.values.max() > 100

def test_dataset_boundaries_isosurface_particles_vectors_errors_geometry(ds):
    d, root, viz = ds
    patches = d.primitives(_leaf(root, "Boundaries/WALL TEMPERATURE/Mesh 1"), 6.0)
    assert len(patches) == 4 and all(isinstance(p, GridSurface) for p in patches)
    assert {p.axis for p in patches} == {"x", "y", "z"}
    (iso,) = d.primitives(_leaf(root, "Isosurfaces/TEMPERATURE/100/Mesh 1"), 6.0)
    assert isinstance(iso, TriMesh) and iso.level == 100.0 and len(iso.faces) > 10
    assert d.primitives(_leaf(root, "Isosurfaces/TEMPERATURE/100/Mesh 1"), 0.0) == []
    (pc,) = d.primitives(_leaf(root, "Particles/DROPS/Mesh 1"), 1.2)
    assert isinstance(pc, PointCloud) and len(pc.points) > 50
    (vec,) = d.primitives(_leaf(root, "2D Slice Vectors/V_Y (Y = 1.5)/Mesh 1"), 6.0)
    assert isinstance(vec, VectorField) and vec.vectors.shape[1] == 3 and vec.values.max() > 0.5
    (err,) = d.primitives(_leaf(root, "Maximum Errors/VELOCITY"), 3.0)
    assert isinstance(err, ErrorBoxes) and len(err.boxes) == 1
    geo = d.primitives(root.find("geometry/fds_actual"), 0.0)
    assert [g.name for g in geo] == ["Obstructions", "Vents", "Open boundaries", "Meshes"] and len(geo[0].boxes) == 3      # the burner is listed once per mesh it touches
    assert d.primitives(root.find("view/Default"), 0.0) == []

def test_dataset_statistics_drive_the_colorbar(ds):
    d, root, viz = ds
    leaves = [l for l in root.leaves() if l.kind == "slice2d" and l.quantity == "TEMPERATURE"]
    s = d.stats("TEMPERATURE", leaves)
    assert s.min == pytest.approx(20.0, abs=0.5) and s.max > 700 and s.p1 <= s.p99 <= s.max
    bar = d.colorbar("TEMPERATURE", "C", leaves)
    assert bar.lo < bar.hi <= s.max + 1
    viz.units.temperature = "F"
    barf = d.colorbar("TEMPERATURE", "C", leaves)
    assert abs(barf.hi - (bar.hi * 1.8 + 32)) < 15            # the range is rounded again in Fahrenheit
    empty = d.stats("NOTHING", leaves)
    assert (empty.min, empty.max) == (0.0, 1.0)

def test_statistics_are_cached_on_disk(copy):
    run = parse_smv(str(copy / "rroom.smv"))
    viz = vm.ResultsVisualization()
    root = build_tree(run, viz)
    leaves = [l for l in root.leaves() if l.kind == "slice2d"]
    first = ResultsDataset(run, viz).stats("TEMPERATURE", leaves)
    assert (copy / "rroom.smv.pyfstats").exists()
    again = ResultsDataset(run, viz).stats("TEMPERATURE", leaves)
    assert again == first

def test_dataset_refresh_sees_new_frames(copy):
    run = parse_smv(str(copy / "rroom.smv"))
    viz = vm.ResultsVisualization()
    root = build_tree(run, viz)
    d = ResultsDataset(run, viz)
    leaf = next(l for l in root.leaves() if l.kind == "slice2d" and l.mesh == 1)
    assert len(d.leaf_times(leaf)) == 13
    f = copy / leaf.files[0]
    n = int(np.prod(d.stream("slice", leaf.files[0]).shape))
    with open(f, "ab") as fh:
        for payload in (struct.pack("<f", 7.0), np.zeros(n, "<f4").tobytes()):
            fh.write(struct.pack("<i", len(payload)) + payload + struct.pack("<i", len(payload)))
    assert d.refresh() == 2 and len(d.leaf_times(leaf)) == 14

# -- the visualization file ------------------------------------------------------------------------------------
def test_visualization_round_trip_with_relative_results_path(tmp_path):
    shutil.copytree(FIX, tmp_path / "results_room")             # same drive as the .pyfdsv, so the path can be relative
    viz = vm.ResultsVisualization(results=str(tmp_path / "results_room" / "rroom.smv"), active=["a/b"],
                                  rendering_mode="wireframe")
    viz.fds.colorbar("TEMPERATURE").colormap = "viridis"
    viz.fds.colorbar("TEMPERATURE").range_mode = "custom"
    viz.fds.colorbar("TEMPERATURE").minimum, viz.fds.colorbar("TEMPERATURE").maximum = 20, 600
    viz.views.append(vm.View("Door", viewpoint=vm.Viewpoint(position=(1, 2, 3))))
    viz.views.append(vm.View("Orbit", tour=vm.Tour(keyframes=[vm.Keyframe(0.0), vm.Keyframe(5.0, transition="stationary")],
                                                    repeat=True), section_box=vm.SectionBox({"x_min": (True, 0.5)})))
    viz.dimensions.append(vm.Dimension((0, 0, 0), (1, 0, 0), "along_x", 0.2))
    viz.labels.append(vm.Label("Burner", (1, 1, 0.2), (1.5, 1.5, 1.0)))
    viz.units.temperature = "F"
    viz.data3d_points.append(vm.Data3DPoint("p1", "g", "TEMPERATURE", (1, 1, 1)))
    viz.csv_files.append(vm.CsvFileRef("x.csv"))
    f = vm.save(viz, str(tmp_path / "case"))
    assert f.endswith(".pyfdsv")
    raw = json.loads(Path(f).read_text())
    assert raw["format"] == "pyfds-visualization" and not Path(raw["results"]).is_absolute() \
        and raw["results"].replace("\\", "/") == "results_room/rroom.smv"
    back = vm.load(f)
    assert Path(back.results).samefile(tmp_path / "results_room" / "rroom.smv") and back.active == ["a/b"] and back.rendering_mode == "wireframe"
    assert back.fds.colorbars["TEMPERATURE"].maximum == 600 and back.views[1].tour.keyframes[1].transition == "stationary"
    assert back.views[1].section_box.active() == {"x_min": 0.5} and back.dimensions[0].mode == "along_x"
    assert back.labels[0].position == (1.5, 1.5, 1.0) and back.units.temperature == "F"
    assert back.data3d_points[0].xyz == (1.0, 1.0, 1.0) and back.csv_files[0].path == "x.csv"
    assert back.problems() == []

def test_visualization_file_moves_with_its_results(tmp_path):
    src = tmp_path / "a"
    shutil.copytree(FIX, src / "run")
    viz = vm.ResultsVisualization(results=str(src / "run" / "rroom.smv"))
    vm.save(viz, str(src / "case.pyfdsv"))
    shutil.move(str(src), str(tmp_path / "b"))
    assert Path(vm.load(str(tmp_path / "b" / "case.pyfdsv")).results).samefile(tmp_path / "b" / "run" / "rroom.smv")

def test_visualization_file_errors_and_tolerance(tmp_path):
    p = tmp_path / "x.pyfdsv"
    for text in ("not json", json.dumps({"format": "other"}), json.dumps({"format": vm.FORMAT, "version": 99})):
        p.write_text(text)
        with pytest.raises(vm.VisualizationFileError):
            vm.load(str(p))
    with pytest.raises(FileNotFoundError):
        vm.load(str(tmp_path / "missing.pyfdsv"))
    p.write_text(json.dumps({"format": vm.FORMAT, "version": 1, "future_field": 1, "units": {"temperature": "F", "x": 2}}))
    v = vm.load(str(p))                                                       # unknown keys ignored, defaults filled
    assert v.units.temperature == "F" and v.geometry_set == "fds_actual"

def test_problems_flags_bad_settings():
    v = vm.ResultsVisualization(geometry_set="x", rendering_mode="y", playback_speed=0)
    v.fds.colorbars["T"] = vm.ColorbarProps(range_mode="custom")
    v.units.temperature = "K"
    v.views = [vm.View("a"), vm.View("a")]
    v.active_view = "zzz"
    v.smoke3d.preset = "nope"
    v.rendering.antialiasing = "bogus"
    msgs = " | ".join(v.problems())
    for needle in ("geometry_set", "rendering_mode", "colorbar T", "temperature unit", "unique", "active view",
                   "preset", "antialiasing", "playback_speed"):
        assert needle in msgs

def test_smoke_presets_and_rendering_presets():
    p = vm.apply_smoke_preset(vm.Smoke3DProps(), "smoke_default")
    assert (p.fire_rendering, p.smoke_determines_fire_transparency) == ("volumetric", False)
    with pytest.raises(ValueError):
        vm.apply_smoke_preset(p, "x")
    r = vm.RenderingPreferences()
    r.max_quality()
    assert r.ambient_occlusion and r.antialiasing == "msaa_4" and r.problems() == []
    r.max_compatibility()
    assert not r.vertex_buffers and r.smoke_renderer == "compatibility" and r.antialiasing == "disabled"
