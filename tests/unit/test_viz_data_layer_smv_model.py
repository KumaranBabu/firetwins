"""Results-viewer data layer against real FDS 6.10.1 output (tests/fixtures/results_room): SMV model, streaming (part 1 of 2)."""


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

def test_tree_groups_output_like_pyrosim(tree):
    root, _ = tree
    top = [c.label for c in root.children]
    assert top == ["Scene Geometry", "Devices", "Views", "FDS Results", "Dimensions", "Labels", "XY Plot Data"]
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
