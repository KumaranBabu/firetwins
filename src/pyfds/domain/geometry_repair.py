"""Triangle-mesh repair and inspection for imported geometry (IMP-05).

Pure functions on ``(verts, faces)``; no project, no Qt. :func:`repair` returns a cleaned copy plus a
report; :func:`inspect` only measures.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Sequence, Tuple

import numpy as np

Vert = Tuple[float, float, float]
Face = Tuple[int, int, int]


def _edge_use(faces: Sequence[Face]) -> Dict[Tuple[int, int], List[int]]:
    use: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for fi, (a, b, c) in enumerate(faces):
        for u, v in ((a, b), (b, c), (c, a)):
            use[(min(u, v), max(u, v))].append(fi)
    return use


def inspect(verts: Sequence[Vert], faces: Sequence[Face], tol: float = 1e-9) -> Dict[str, object]:
    """Counts of problems: degenerate and duplicate triangles, open and non-manifold edges, and
    whether the surface is closed. ``volume`` is the signed volume (negative = inward-facing)."""
    v = np.asarray(verts, dtype=float).reshape(-1, 3)
    f = np.asarray(faces, dtype=int).reshape(-1, 3)
    degenerate = 0
    if len(f):
        cross = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        area2 = np.linalg.norm(cross, axis=1)
        degenerate = int(np.count_nonzero((area2 <= tol) | (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])))
    seen = set()
    duplicate = 0
    for tri in faces:
        key = tuple(sorted(tri))
        duplicate += key in seen
        seen.add(key)
    use = _edge_use(faces)
    open_edges = sum(1 for fs in use.values() if len(fs) == 1)
    non_manifold = sum(1 for fs in use.values() if len(fs) > 2)
    volume = 0.0
    if len(f):
        volume = float(np.einsum("ij,ij->i", v[f[:, 0]], np.cross(v[f[:, 1]], v[f[:, 2]])).sum() / 6.0)
    return {"vertices": len(v), "triangles": len(f), "degenerate": degenerate, "duplicate": duplicate,
            "open_edges": open_edges, "non_manifold_edges": non_manifold,
            "closed": bool(len(f)) and open_edges == 0 and non_manifold == 0, "volume": volume}


def _weld(verts: np.ndarray, faces: np.ndarray, tol: float):
    if tol <= 0 or not len(verts):
        return verts, faces
    keys = np.round(verts / tol).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    return verts[first], inverse[faces]


def _orient(faces: np.ndarray) -> Tuple[np.ndarray, int]:
    """Flip triangles so neighbours share edges in opposite directions (consistent winding)."""
    faces = faces.copy()
    n = len(faces)
    use = _edge_use([tuple(t) for t in faces])
    seen = np.zeros(n, dtype=bool)
    flipped = 0

    def directed(fi):
        a, b, c = faces[fi]
        return {(a, b), (b, c), (c, a)}

    for start in range(n):
        if seen[start]:
            continue
        seen[start] = True
        queue = deque([start])
        while queue:
            fi = queue.popleft()
            mine = directed(fi)
            a, b, c = faces[fi]
            for u, v in ((a, b), (b, c), (c, a)):
                fs = use[(min(u, v), max(u, v))]
                if len(fs) != 2:
                    continue
                other = fs[0] if fs[1] == fi else fs[1]
                if seen[other]:
                    continue
                seen[other] = True
                if directed(other) & mine:          # same direction on a shared edge -> flip
                    faces[other] = faces[other][::-1]
                    flipped += 1
                queue.append(other)
    return faces, flipped


def repair(verts: Sequence[Vert], faces: Sequence[Face], *, weld_tol: float = 1e-6,
           orient: bool = True, outward: bool = True) -> Tuple[List[Vert], List[Face], Dict[str, object]]:
    """Clean a triangle mesh and say what was done.

    Steps: weld vertices closer than *weld_tol*; drop degenerate and duplicate triangles; drop unused
    vertices; make the winding consistent (*orient*); flip a closed mesh whose volume is negative so
    its normals point outward (*outward*). Returns ``(verts, faces, report)``.
    """
    before = inspect(verts, faces)
    v = np.asarray(verts, dtype=float).reshape(-1, 3)
    f = np.asarray(faces, dtype=int).reshape(-1, 3)
    v, f = _weld(v, f, weld_tol)
    keep, seen = [], set()
    removed_dup = 0
    for i, (a, b, c) in enumerate(f):
        if a == b or b == c or a == c:
            continue
        if np.linalg.norm(np.cross(v[b] - v[a], v[c] - v[a])) <= 1e-12:
            continue
        key = tuple(sorted((a, b, c)))
        if key in seen:
            removed_dup += 1
            continue
        seen.add(key)
        keep.append(i)
    removed_degenerate = len(f) - len(keep) - removed_dup
    f = f[keep] if keep else f[:0]
    used = np.unique(f)
    remap = -np.ones(len(v), dtype=int)
    remap[used] = np.arange(len(used))
    v, f = v[used], remap[f]
    flipped = 0
    if orient and len(f):
        f, flipped = _orient(f)
    mid = inspect(v, f)
    inverted = False
    if outward and len(f) and mid["closed"] and mid["volume"] < 0:
        f = f[:, ::-1].copy()
        inverted = True
    out_v = [tuple(map(float, p)) for p in v]
    out_f = [tuple(map(int, t)) for t in f]
    after = inspect(out_v, out_f)
    report = {"before": before, "after": after, "welded_vertices": before["vertices"] - len(out_v),
              "removed_degenerate": removed_degenerate, "removed_duplicate": removed_dup,
              "flipped_triangles": flipped, "inverted_whole_mesh": inverted}
    return out_v, out_f, report
