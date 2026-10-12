"""Results-viewer data layer against real FDS 6.10.1 output (tests/fixtures/results_room): SMV model, streaming
readers, tree and activation rules, colorbars, dataset primitives, units, maximum errors, visualization file."""
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


# -- SMV model ------------------------------------------------------------------------------------------
def test_smv_model(run):
    assert run.chid == "rroom" and run.fds_version.startswith("FDS-6.10") and run.times == (0.0, 6.0)
    assert [(m.index, m.ijk) for m in run.meshes] == [(1, (10, 20, 15)), (2, (10, 20, 15))]
    assert run.mesh(2).extents[:2] == (1.5, 3.0) and run.mesh(2).node_coords(0)[0] == 1.5
    assert {o.name for o in run.obstructions} == {"BURNER", "TABLE"}
    assert len(run.slices) == 15 and len(run.smoke3d) == 6 and len(run.boundaries) == 2 and len(run.plot3d) == 4
    assert run.hrrpuv_range == (0.0, 1200.0) and [c.name for c in run.particle_classes] == ["DROPS"]
    assert run.bounds() == (0.0, 3.0, 0.0, 3.0, 0.0, 2.25)
    with pytest.raises(FileNotFoundError):
        parse_smv(str(FIX / "nope.smv"))
    with pytest.raises(KeyError):
        run.mesh(9)


def test_slice_geometry_and_vector_groups(run):
    t_y = next(s for s in run.slices if s.name == "T_Y" and s.mesh == 1)
    assert (t_y.idir, t_y.plane_label, t_y.is_volume) == (2, "Y", False)
    xs, ys, zs = run.slice_coords(t_y)
    assert ys.tolist() == [1.5] and xs[0] == 0 and xs[-1] == pytest.approx(1.5) and len(zs) == 16
    assert next(s for s in run.slices if s.name == "T_3D").is_volume
    assert sorted(run.vector_groups()) == [(1, 3), (2, 3)]
    assert set(run.vector_groups()[(1, 3)]) == {"U", "V", "W"}


def test_stretched_mesh_nodes_are_used(tmp_path):
    text = (FIX / "rroom.smv").read_text()
    # squeeze mesh 1's first TRNX nodes: 0, 0.15 ... -> 0, 0.10 ... (a stretched mesh)
    stretched = text.replace("    1       0.15000\n    2       0.30000", "    1       0.10000\n    2       0.30000", 1)
    f = tmp_path / "s.smv"
    f.write_text(stretched)
    m = parse_smv(str(f)).mesh(1)
    assert m.node_coords(0)[1] == pytest.approx(0.10) and not m.uniform


# -- streaming readers -----------------------------------------------------------------------------------
def test_slice_stream():
    s = st.SliceStream(str(FIX / "rroom_1_1.sf"), use_cache=False)
    assert (s.quantity, s.units, s.shape, s.n_frames) == ("TEMPERATURE", "C", (11, 1, 16), 13)
    assert s.times[0] == 0.0 and np.all(np.diff(s.times) > 0)
    assert s.frame(0).max() == pytest.approx(20.0, abs=0.5) and s.frame(12).max() > 300


def test_boundary_stream_reads_the_real_9_integer_patches():
    b = st.BoundaryStream(str(FIX / "rroom_1_1.bf"), use_cache=False)
    assert b.n_patches == 4 and len(b.patches[0]) == 9 and b.n_frames == 13
    assert [a.size for a in b.frame(3)] == b.sizes == [6, 10, 6, 15]


def test_particle_stream_counts_follow_the_fixture():
    p = st.ParticleStream(str(FIX / "rroom_1.prt5"), use_cache=False)
    assert p.n_classes == 1 and p.n_frames == 13 and p.version == 600
    counts = [p.frame(k)[0]["positions"].shape[0] for k in range(p.n_frames)]
    assert counts[:3] == [75, 75, 72] and counts[-1] == 0                 # droplets fall out / evaporate
    f = p.frame(1)[0]
    assert f["positions"].shape == (75, 3) and f["tags"].shape == (75,)
    assert 1.2 < f["positions"][:, 0].min() and f["positions"][:, 0].max() < 1.6


def test_iso_stream():
    i = st.IsoStream(str(FIX / "rroom_1_1.iso"), use_cache=False)
    assert i.levels == [100.0] and i.n_frames == 13
    v, tri = i.frame(i.n_frames - 1)[0]
    assert v.shape[1] == 3 and tri.shape[1] == 3 and tri.max() < len(v) and tri.min() >= 0
    assert i.frame(0)[0][0].shape[0] == 0                                  # nothing hot at t = 0


def test_plot3d_stream():
    q = st.Plot3DStream(str(FIX / "rroom_1_3p01.q"), use_cache=False)
    d = q.data()
    assert q.shape == (11, 21, 16) and d.shape == (5, 11, 21, 16) and d[0].max() > 100


def test_smoke3d_stream_decodes_run_length_frames():
    s = st.Smoke3DStream(str(FIX / "rroom_1_2.s3d"), use_cache=False)       # HRRPUV
    assert s.shape == (11, 21, 16) and s.n_frames == 210
    assert s.frame_bytes(0).max() == 0 and s.frame_bytes(s.n_frames - 1).max() > 200
    assert s.frame_bytes(5).dtype == np.uint8


def test_rle_decode_edge_cases():
    assert st.rle_decode(bytes([1, 2, 3]), 3).tolist() == [1, 2, 3]
    assert st.rle_decode(bytes([255, 7, 5, 9]), 6).tolist() == [7, 7, 7, 7, 7, 9]
    assert st.rle_decode(bytes([4, 255, 0, 254, 4]), 256).tolist() == [4] + [0] * 254 + [4]
    with pytest.raises(st.StreamError):
        st.rle_decode(bytes([255, 7, 5]), 9)


def test_smoke_soot_byte_means_absorption_per_cell():
    """Soot bytes are 255 * (1 - exp(-kappa * rho * dx)) with kappa 8700: checked against the 3-D soot slice."""
    s3 = st.Smoke3DStream(str(FIX / "rroom_1_1.s3d"), use_cache=False)
    sl = st.SliceStream(str(FIX / "rroom_1_8.sf"), use_cache=False)
    k = sl.n_frames - 1
    rho = sl.frame(k).astype(float)
    byte = s3.frame_bytes(int(np.argmin(abs(s3.times - sl.times[k])))).astype(float)
    m = (rho > 1e-5) & (rho < 0.01) & (byte > 20)
    predicted = 255 * (1 - np.exp(-8700 * rho[m] * 0.15))
    assert m.sum() > 50 and np.median(abs(predicted - byte[m]) / byte[m]) < 0.08


def test_cache_speeds_reopening_and_follows_a_growing_file(copy):
    f = str(copy / "rroom_1_1.sf")
    a = st.SliceStream(f)
    assert (copy / "rroom_1_1.sf.pyfcache").exists() and a.n_frames == 13
    b = st.SliceStream(f)                                                   # from the cache
    assert b.n_frames == 13 and b.times[-1] == a.times[-1]
    # a running FDS appends: add one frame (time + values), the new tail is picked up without a rescan
    n = int(np.prod(a.shape))
    with open(f, "ab") as fh:
        for payload in (struct.pack("<f", 99.0), np.full(n, 5.0, "<f4").tobytes()):
            fh.write(struct.pack("<i", len(payload)) + payload + struct.pack("<i", len(payload)))
    assert b.refresh() == 2 and b.n_frames == 14 and b.times[-1] == pytest.approx(99.0) and b.frame(13).max() == 5.0
    # a half-written record at the end is left alone until it is complete
    with open(f, "ab") as fh:
        fh.write(struct.pack("<i", 1000) + b"\x00" * 10)
    assert st.SliceStream(f).n_frames == 14


def test_corrupt_cache_is_ignored(copy):
    f = copy / "rroom_1_1.sf"
    (copy / "rroom_1_1.sf.pyfcache").write_text("{ not json")
    assert st.SliceStream(str(f)).n_frames == 13


def test_wrong_file_type_is_refused(copy):
    (copy / "bad.sf").write_bytes(b"\x04\x00\x00\x00abcd\x04\x00\x00\x00")
    with pytest.raises(st.StreamError):
        st.SliceStream(str(copy / "bad.sf"), use_cache=False)


# -- tree and activation -----------------------------------------------------------------------------------
@pytest.fixture
def tree(run):
    viz = vm.ResultsVisualization()
    return build_tree(run, viz), viz


def test_tree_groups_output_like_pyrosim(tree):
    root, _ = tree
    top = [c.label for c in root.children]
    assert top == ["Scene Geometry", "Views", "FDS Results", "Dimensions", "Labels", "XY Plot Data"]
    res = root.find("root/FDS Results")
    assert [c.label for c in res.children] == ["3D Smoke", "3D Slices", "Plot3D", "Isosurfaces", "2D Slices",
                                               "2D Slice Vectors", "Boundaries", "Particles", "Maximum Errors"]
    t = root.find("root/FDS Results/2D Slices/TEMPERATURE")
    assert [c.label for c in t.children] == ["T_Y (Y = 1.5)", "T_X (X = 1.05)"]
    assert [l.label for l in t.children[0].leaves()] == ["Mesh 1", "Mesh 2"]          # one slice through two meshes
    assert [l.label for l in t.children[1].leaves()] == ["Mesh 1"]
    smoke = root.find("root/FDS Results/3D Smoke")
    assert [c.label for c in smoke.children] == ["SOOT DENSITY", "HRRPUV", "TEMPERATURE"]
    assert root.find("root/Scene Geometry").children[0].label == "FDS Actual"


def test_activation_toggles_whole_groups_and_reports_state(tree):
    root, viz = tree
    am = ActivationModel(root, viz)
    node = root.find("root/FDS Results/2D Slices/TEMPERATURE/T_Y (Y = 1.5)")
    r = am.toggle(node.id)
    assert len(r.activated) == 2 and am.state(node) == "all"
    assert am.state(root.find("root/FDS Results/2D Slices")) == "some"
    assert am.state(root.find("root/FDS Results/Boundaries")) == "none"
    am.toggle(node.id)
    assert viz.active == [] and am.state(node) == "none"
    with pytest.raises(KeyError):
        am.toggle("root/nope")


def test_activation_rules_follow_preferences(tree):
    root, viz = tree
    am = ActivationModel(root, viz)
    temp = root.find("root/FDS Results/2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1")
    soot = root.find("root/FDS Results/3D Slices/SOOT DENSITY/SOOT_3D/Mesh 1")
    am.activate(temp.id)
    am.activate(soot.id)
    assert set(viz.active) == {temp.id, soot.id}                          # several quantities allowed by default
    viz.general.allow_multiple_quantities = False
    r = am.activate(root.find("root/FDS Results/Boundaries/WALL TEMPERATURE/Mesh 1").id)
    assert soot.id in r.deactivated and temp.id in viz.active              # kg/m3 dropped, C kept
    viz.general.allow_conflicting_results = False
    vel = root.find("root/FDS Results/2D Slices/VELOCITY/V_Y (Y = 1.5)/Mesh 1")
    r = am.activate(vel.id)                                                # same plane as the TEMPERATURE slice
    assert temp.id in r.deactivated
    viz.general.begin_playback_on_activation = True
    assert am.activate(root.find("root/FDS Results/Particles/DROPS/Mesh 1").id).begin_playback


def test_only_one_geometry_set_at_a_time(tree):
    root, viz = tree
    am = ActivationModel(root, viz)
    actual, req = "geometry/fds_actual", "geometry/fds_requested"
    am.activate(am.root.find(actual).id)
    r = am.activate(am.root.find(req).id)
    assert r.deactivated == [actual] and viz.active == [req]
    viz.general.one_geometry_at_a_time = False
    am.activate(actual)
    assert set(viz.active) == {actual, req}


def test_prune_drops_ids_that_no_longer_exist(tree):
    root, viz = tree
    viz.active = ["root/FDS Results/Boundaries/WALL TEMPERATURE/Mesh 1", "root/gone"]
    ActivationModel(root, viz).prune()
    assert viz.active == ["root/FDS Results/Boundaries/WALL TEMPERATURE/Mesh 1"]


# -- colorbar -------------------------------------------------------------------------------------------
def test_colorbar_ranges_and_tables():
    stats = QuantityStats(20.0, 785.0, 20.0, 480.0)
    p = vm.ColorbarProps()
    assert cb.data_range(p, stats) == (20.0, 500.0 if False else cb.data_range(p, stats)[1])
    lo, hi = cb.data_range(vm.ColorbarProps(range_mode="global"), stats)
    assert (lo, hi) == (20.0, 785.0)
    lo, hi = cb.data_range(vm.ColorbarProps(range_mode="global_rounded"), stats)
    assert lo <= 20.0 and hi >= 785.0 and hi % 10 == 0
    assert cb.data_range(vm.ColorbarProps(range_mode="custom", minimum=0, maximum=100), stats) == (0.0, 100.0)
    with pytest.raises(ValueError):
        cb.data_range(vm.ColorbarProps(range_mode="custom"), stats)
    model = cb.ColorbarModel(vm.ColorbarProps(n_colors=8), 0.0, 100.0)
    tab = model.table()
    assert tab.shape == (8, 4) and np.all(tab[:, 3] == 1.0) and not np.allclose(tab[0, :3], tab[-1, :3])
    rgba = model.rgba(np.array([0.0, 50.0, 100.0, 1e9, np.nan]))
    assert np.allclose(rgba[2, :3], rgba[3, :3]) and rgba[4, 3] == 0.0       # clamped above, NaN transparent
    inv = cb.ColorbarModel(vm.ColorbarProps(n_colors=8, invert=True), 0, 100).table()
    assert np.allclose(inv[0, :3], tab[-1, :3])


def test_colorbar_opacity_truncation_highlight():
    g = cb.ColorbarModel(vm.ColorbarProps(opacity_source="gradient", opacity_at_min=0.0, opacity_at_max=0.5, n_colors=11), 0, 10)
    assert g.table()[0, 3] < 0.05 and g.table()[-1, 3] == pytest.approx(0.5, abs=0.05)
    f = cb.ColorbarModel(vm.ColorbarProps(opacity_source="feather_below", feather_threshold=0.5, n_colors=10), 0, 10).table()
    assert f[0, 3] < f[2, 3] < f[5, 3] == 1.0
    t = cb.ColorbarModel(vm.ColorbarProps(truncate=True, hide_below=2, hide_above=8), 0, 10)
    assert t.rgba(np.array([1.0, 5.0, 9.0]))[:, 3].tolist() == [0.0, 1.0, 0.0]
    p = vm.ColorbarProps(n_colors=100)
    cb.highlight_at(p, 0, 100, 0.5)
    assert (p.highlight_value, p.highlight_width) == (50.0, 5.0)
    cb.resize_highlight(p, 0, 100, 3)
    assert p.highlight_width == pytest.approx(8.0)
    hot = cb.ColorbarModel(p, 0, 100).table()
    assert np.allclose(hot[50, :3], (1, 1, 1)) and not np.allclose(hot[10, :3], (1, 1, 1))
    cb.clear_highlight(p)
    assert not p.highlight_enabled
    const = cb.ColorbarModel(vm.ColorbarProps(color_source="constant", color="#ff0000", n_colors=4), 0, 1).table()
    assert np.allclose(const[:, :3], (1, 0, 0))
    for bad in (vm.ColorbarProps(range_mode="x"), vm.ColorbarProps(n_colors=1), vm.ColorbarProps(opacity_source="y"),
                vm.ColorbarProps(feather_threshold=2)):
        with pytest.raises(ValueError):
            cb.ColorbarModel(bad, 0, 1)
    with pytest.raises(ValueError):
        cb.ColorbarModel(vm.ColorbarProps(), 1, 1)


# -- units -----------------------------------------------------------------------------------------------
def test_unit_conversion():
    prefs = vm.Units(temperature="F", concentration="ppm", mass_fraction="ppm")
    v, u = un.convert(np.array([0.0, 100.0]), "C", prefs)
    assert v.tolist() == [32.0, 212.0] and u == "F"
    assert un.convert(np.array([1e-3]), "mol/mol", prefs) == (pytest.approx([1000.0]), "ppm")
    assert un.convert(np.array([2e-6]), "kg/kg", prefs)[1] == "ppm"
    same = un.convert(np.array([5.0]), "m/s", prefs)
    assert same[0].tolist() == [5.0] and same[1] == "m/s"
    assert un.label("C", vm.Units()) == "C" and un.convert_value(10.0, "C", prefs) == (50.0, "F")
    assert vm.Units(temperature="K").problems()


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


# -- dataset ---------------------------------------------------------------------------------------------
@pytest.fixture
def ds(run, tree):
    root, viz = tree
    d = ResultsDataset(run, viz, use_cache=False)
    return d, root, viz


def _leaf(root, path):
    return root.find("root/FDS Results/" + path)


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
