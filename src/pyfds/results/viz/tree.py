"""The Navigation View: the tree of everything a loaded run can show, and the rules for switching it on.

``build_tree`` turns an :class:`~pyfds.results.viz.fds_run.FdsRun` (plus the visualization's own views,
annotations and CSV files) into a tree of :class:`NavNode`. Output that FDS split over several meshes is
grouped under one entry per quantity / slice / value, as in PyroSim Results. ``ActivationModel`` decides what
happens when a node is double-clicked: it switches the leaves under it on or off and applies the
preferences ("allow several quantities", "allow geometrically conflicting results", "one geometry set at a
time").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple

from .fds_run import FdsRun, SliceFile
from .model import GeneralPreferences, ResultsVisualization

#: leaf kinds that are FDS results (they take part in the quantity / geometry rules and own colorbars)
RESULT_KINDS = {"smoke3d", "slice3d", "plot3d", "isosurface", "slice2d", "slice_vectors", "boundary", "particles",
                "max_error", "data3d_point", "data3d_slice", "data3d_iso"}
GEOMETRY_LABELS = {"fds_actual": "FDS Actual", "fds_requested": "FDS Requested",
                   "pyfds_geometry": "PyFDS Geometry", "ge1": "GE1"}


def _clean(label: str) -> str:
    return label.replace("/", "|")


@dataclass
class NavNode:
    id: str
    label: str
    kind: str = "group"                 # "group" or a leaf kind (geometry, view, smoke3d, slice2d, ...)
    children: List["NavNode"] = field(default_factory=list)
    quantity: str = ""
    units: str = ""
    mesh: int = 0
    files: List[str] = field(default_factory=list)      # result files (with their mesh in ``meshes``)
    meshes: List[int] = field(default_factory=list)
    geometry_key: Optional[Tuple] = None
    data: Dict[str, object] = field(default_factory=dict)

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def leaves(self) -> Iterator["NavNode"]:
        if self.is_leaf:
            if self.kind != "group":
                yield self
            return
        for c in self.children:
            yield from c.leaves()

    def walk(self) -> Iterator["NavNode"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def find(self, node_id: str) -> Optional["NavNode"]:
        for n in self.walk():
            if n.id == node_id:
                return n
        return None


def _group(parent: NavNode, label: str, kind: str = "group", **kw) -> NavNode:
    node = NavNode(f"{parent.id}/{_clean(label)}", label, kind, **kw)
    parent.children.append(node)
    return node


def _plane_label(run: FdsRun, s: SliceFile) -> str:
    if s.is_volume:
        return s.name or "3D"
    xs, ys, zs = run.slice_coords(s)
    coord = {1: xs, 2: ys, 3: zs}[s.idir][0]
    return f"{s.name or s.quantity} ({'XYZ'[s.idir - 1]} = {coord:g})"


def build_tree(run: Optional[FdsRun], viz: ResultsVisualization, have_project_geometry: bool = False) -> NavNode:
    root = NavNode("root", "Project")
    # -- scene geometry ------------------------------------------------------------------
    geo = _group(root, "Scene Geometry")
    if run is not None:
        if run.obstructions or run.vents or run.meshes:
            geo.children.append(NavNode("geometry/fds_actual", GEOMETRY_LABELS["fds_actual"], "geometry"))
        if run.input_file and (Path(run.input_file).exists() or (run.directory / (run.chid + ".fds")).exists()):
            geo.children.append(NavNode("geometry/fds_requested", GEOMETRY_LABELS["fds_requested"], "geometry"))
        if any(run.directory.glob("*.ge1")):
            geo.children.append(NavNode("geometry/ge1", GEOMETRY_LABELS["ge1"], "geometry"))
    if have_project_geometry:
        geo.children.append(NavNode("geometry/pyfds_geometry", GEOMETRY_LABELS["pyfds_geometry"], "geometry"))
    # -- views --------------------------------------------------------------------------------
    views = _group(root, "Views")
    views.children.append(NavNode("view/Default", "Default", "view"))
    for v in viz.views:
        label = v.name if v.origin == "pyfds" else f"[FDS] {v.name}"
        views.children.append(NavNode(f"view/{_clean(v.name)}", label, "view", data={"tour": v.tour is not None}))
    if run is not None:
        _fds_results(root, run, viz)
    # -- annotations and plot data ---------------------------------------------------------------
    dims = _group(root, "Dimensions")
    for i, d in enumerate(viz.dimensions):
        dims.children.append(NavNode(f"dimension/{i}", f"Dimension {i + 1}", "dimension", data={"index": i}))
    labels = _group(root, "Labels")
    for i, lab in enumerate(viz.labels):
        labels.children.append(NavNode(f"label/{i}", lab.text.splitlines()[0] if lab.text else f"Label {i + 1}", "label", data={"index": i}))
    xy = _group(root, "XY Plot Data")
    for c in viz.csv_files:
        node = NavNode(f"csv/{_clean(Path(c.path).name)}", Path(c.path).name, "csv", data={"path": c.path})
        xy.children.append(node)
    return root


def _data3d_groups(qn: NavNode, viz: ResultsVisualization) -> None:
    """Points / Slices / Isosurfaces made from a 3-D dataset, listed under its quantity (kept in the visualization)."""
    mine_p = [o for o in viz.data3d_points if o.group == qn.id]
    mine_s = [o for o in viz.data3d_slices if o.group == qn.id]
    mine_i = [o for o in viz.data3d_isos if o.group == qn.id]
    for label, kind, items in (("Points", "data3d_point", mine_p), ("Slices", "data3d_slice", mine_s),
                               ("Isosurfaces", "data3d_iso", mine_i)):
        g = _group(qn, label)
        for o in items:
            g.children.append(NavNode(f"{g.id}/{_clean(o.id)}", o.id, kind, quantity=o.quantity,
                                      data={"obj_id": o.id, "group": qn.id}))


def _fds_results(root: NavNode, run: FdsRun, viz: ResultsVisualization) -> None:
    res = _group(root, "FDS Results")
    # 3D smoke: one entry per quantity, per mesh
    if run.smoke3d:
        g = _group(res, "3D Smoke")
        for q in sorted({o.quantity for o in run.smoke3d}, key=lambda x: (x != "SOOT DENSITY", x != "HRRPUV", x)):
            qn = _group(g, q)
            for o in sorted((o for o in run.smoke3d if o.quantity == q), key=lambda o: o.mesh):
                qn.children.append(NavNode(f"{qn.id}/Mesh {o.mesh}", f"Mesh {o.mesh}", "smoke3d", quantity=q,
                                           units=o.units, mesh=o.mesh, files=[o.file], meshes=[o.mesh]))
    # 3D slices and 2D slices
    vol = [s for s in run.slices if s.is_volume]
    planar = [s for s in run.slices if not s.is_volume]
    vector_files = {(m, sid, tag): s for (m, sid), grp in run.vector_groups().items() for tag, s in grp.items()}
    vec_set = {id(s) for s in vector_files.values()}
    if vol:
        g = _group(res, "3D Slices")
        for q in sorted({s.quantity for s in vol}):
            qn = _group(g, q)
            for name in sorted({s.name for s in vol if s.quantity == q}):
                nn = _group(qn, name or q)
                for s in sorted((s for s in vol if s.quantity == q and s.name == name), key=lambda s: s.mesh):
                    nn.children.append(NavNode(f"{nn.id}/Mesh {s.mesh}", f"Mesh {s.mesh}", "slice3d", quantity=q,
                                               units=s.units, mesh=s.mesh, files=[s.file], meshes=[s.mesh]))
            _data3d_groups(qn, viz)
    if run.plot3d:
        g = _group(res, "Plot3D")
        qs = run.plot3d[0].quantities
        for qi, (q, short, units) in enumerate(qs):
            if not q:
                continue
            qn = _group(g, q)
            for mesh in sorted({p.mesh for p in run.plot3d}):
                files = [p.file for p in sorted(run.plot3d, key=lambda p: p.time) if p.mesh == mesh]
                qn.children.append(NavNode(f"{qn.id}/Mesh {mesh}", f"Mesh {mesh}", "plot3d", quantity=q, units=units,
                                           mesh=mesh, files=files, meshes=[mesh] * len(files), data={"index": qi}))
            _data3d_groups(qn, viz)
    if run.isosurfaces:
        g = _group(res, "Isosurfaces")
        for q in sorted({o.quantity for o in run.isosurfaces}):
            qn = _group(g, q)
            for o in sorted((o for o in run.isosurfaces if o.quantity == q), key=lambda o: o.mesh):
                label = _iso_label(run, o)
                vn = next((c for c in qn.children if c.label == label), None) or _group(qn, label)
                vn.children.append(NavNode(f"{vn.id}/Mesh {o.mesh}", f"Mesh {o.mesh}", "isosurface", quantity=q,
                                           units=o.units, mesh=o.mesh, files=[o.file], meshes=[o.mesh]))
    if planar:
        g = _group(res, "2D Slices")
        plain = [s for s in planar if id(s) not in vec_set or s.quantity.upper() == "VELOCITY"]
        for q in sorted({s.quantity for s in plain}):
            qn = _group(g, q)
            seen: Dict[str, NavNode] = {}
            for s in sorted((s for s in plain if s.quantity == q), key=lambda s: (s.slice_id, s.mesh)):
                label = _plane_label(run, s)
                sn = seen.get(label) or seen.setdefault(label, _group(qn, label))
                xs, ys, zs = run.slice_coords(s)
                key = ("plane", s.idir, round(float({1: xs, 2: ys, 3: zs}[s.idir][0]), 4))
                sn.children.append(NavNode(f"{sn.id}/Mesh {s.mesh}", f"Mesh {s.mesh}", "slice2d", quantity=q,
                                           units=s.units, mesh=s.mesh, files=[s.file], meshes=[s.mesh],
                                           geometry_key=key, data={"idir": s.idir, "slice_id": s.slice_id}))
    if run.vector_groups():
        g = _group(res, "2D Slice Vectors")
        for (mesh, sid), grp in sorted(run.vector_groups().items()):
            u = grp["U"]
            label = _plane_label(run, u)
            node = next((c for c in g.children if c.label == label), None) or _group(g, label)
            node.children.append(NavNode(f"{node.id}/Mesh {mesh}", f"Mesh {mesh}", "slice_vectors", quantity="VELOCITY",
                                         units="m/s", mesh=mesh, files=[grp["U"].file, grp["V"].file, grp["W"].file],
                                         meshes=[mesh] * 3, data={"idir": u.idir, "slice_id": sid}))
    if run.boundaries:
        g = _group(res, "Boundaries")
        for q in sorted({o.quantity for o in run.boundaries}):
            qn = _group(g, q)
            for o in sorted((o for o in run.boundaries if o.quantity == q), key=lambda o: o.mesh):
                qn.children.append(NavNode(f"{qn.id}/Mesh {o.mesh}", f"Mesh {o.mesh}", "boundary", quantity=q,
                                           units=o.units, mesh=o.mesh, files=[o.file], meshes=[o.mesh],
                                           geometry_key=("boundary", o.mesh)))
    if run.particles:
        g = _group(res, "Particles")
        for ci, cls in enumerate(run.particle_classes or []):
            cn = _group(g, cls.name)
            for o in sorted(run.particles, key=lambda o: o.mesh):
                cn.children.append(NavNode(f"{cn.id}/Mesh {o.mesh}", f"Mesh {o.mesh}", "particles", mesh=o.mesh,
                                           files=[o.file], meshes=[o.mesh], data={"class_index": ci, "class": cls.name}))
    g = _group(res, "Maximum Errors")
    for q in ("PRESSURE", "VELOCITY"):
        g.children.append(NavNode(f"{g.id}/{q}", q, "max_error", quantity=q + " ERROR", data={"which": q}))
    if not any(c.children for c in g.children) and not run.directory.joinpath(run.chid + ".out").exists():
        res.children.remove(g)


def _iso_label(run: FdsRun, o) -> str:
    try:
        from .streams import IsoStream
        s = IsoStream(str(run.resolve(o.file)), use_cache=False)
        return " / ".join(f"{v:g}" for v in s.levels) or "iso"
    except Exception:
        return "iso"


# -- activation ----------------------------------------------------------------------------------------
@dataclass
class ActivationResult:
    activated: List[str] = field(default_factory=list)
    deactivated: List[str] = field(default_factory=list)
    begin_playback: bool = False


class ActivationModel:
    """Which leaves are shown, and the preference rules applied when something is switched on."""

    def __init__(self, root: NavNode, viz: ResultsVisualization) -> None:
        self.root = root
        self.viz = viz

    @property
    def prefs(self) -> GeneralPreferences:
        return self.viz.general

    def leaf_ids(self) -> Set[str]:
        return {n.id for n in self.root.leaves()}

    def prune(self) -> None:
        """Drop active ids that no longer exist (after loading other results)."""
        known = self.leaf_ids()
        self.viz.active = [a for a in self.viz.active if a in known]

    def is_active(self, node_id: str) -> bool:
        return node_id in self.viz.active

    def state(self, node: NavNode) -> str:
        """``none``, ``some`` or ``all`` of the leaves under *node* are active (drives bold / partial display)."""
        leaves = [l.id for l in node.leaves()]
        if not leaves:
            return "none"
        n = sum(1 for l in leaves if l in self.viz.active)
        return "all" if n == len(leaves) else "some" if n else "none"

    def active_nodes(self) -> List[NavNode]:
        by_id = {n.id: n for n in self.root.leaves()}
        return [by_id[a] for a in self.viz.active if a in by_id]

    # -- changes ----------------------------------------------------------------------------------
    def toggle(self, node_id: str) -> ActivationResult:
        node = self.root.find(node_id)
        if node is None:
            raise KeyError(f"no node {node_id!r}")
        leaves = list(node.leaves())
        if not leaves:
            return ActivationResult()
        if all(l.id in self.viz.active for l in leaves):
            return self.deactivate(node_id)
        return self.activate(node_id)

    def activate(self, node_id: str) -> ActivationResult:
        node = self.root.find(node_id)
        if node is None:
            raise KeyError(f"no node {node_id!r}")
        res = ActivationResult()
        for leaf in node.leaves():
            if leaf.id in self.viz.active:
                continue
            res.deactivated += self._make_room(leaf)
            self.viz.active.append(leaf.id)
            res.activated.append(leaf.id)
        res.deactivated = [d for d in res.deactivated if d not in res.activated]
        res.begin_playback = bool(res.activated) and self.prefs.begin_playback_on_activation
        return res

    def deactivate(self, node_id: str) -> ActivationResult:
        node = self.root.find(node_id)
        if node is None:
            raise KeyError(f"no node {node_id!r}")
        gone = [l.id for l in node.leaves() if l.id in self.viz.active]
        self.viz.active = [a for a in self.viz.active if a not in gone]
        return ActivationResult(deactivated=gone)

    def _make_room(self, leaf: NavNode) -> List[str]:
        """Apply the preference rules before *leaf* is switched on; returns the ids switched off."""
        by_id = {n.id: n for n in self.root.leaves()}
        out = []
        for aid in list(self.viz.active):
            other = by_id.get(aid)
            if other is None:
                continue
            drop = False
            if leaf.kind == "geometry" and other.kind == "geometry" and self.prefs.one_geometry_at_a_time:
                drop = True
            elif leaf.kind in RESULT_KINDS and other.kind in RESULT_KINDS:
                if not self.prefs.allow_multiple_quantities and other.units != leaf.units and leaf.units and other.units:
                    drop = True
                if (not self.prefs.allow_conflicting_results and leaf.geometry_key is not None
                        and leaf.geometry_key == other.geometry_key and leaf.quantity != other.quantity):
                    drop = True
            if drop:
                self.viz.active.remove(aid)
                out.append(aid)
        return out
