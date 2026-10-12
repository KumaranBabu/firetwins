"""Draws an ``api.viewer`` :class:`Frame` into a PyVista plotter.

Only this module (and the window) know about VTK; everything it draws comes from the data layer. It works
on any ``pyvista.Plotter`` - a ``QtInteractor`` in the window, an off-screen plotter for screenshots, movies
and tests. Each ``draw`` clears and rebuilds the actors (cheap for the sizes involved) and keeps the camera
unless asked to apply one.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pyvista as pv

from pyfds.api.viz import model as vm
from pyfds.api.viz import (ErrorBoxes, GeometryBoxes, GridSurface, PointCloud, RectilinearVolume,
                                          TriMesh, VectorField)

from .quality import apply_quality, volume_mapper

BACKGROUND = "#1c1e22"


def _lut(bar, name: str = "q") -> pv.LookupTable:
    tab = (bar.table() * 255).astype(np.uint8)
    lut = pv.LookupTable(values=tab, scalar_range=(bar.lo, bar.hi), n_values=len(tab))
    lut.below_range_color = None
    lut.above_range_color = None
    return lut


def _box_mesh(boxes) -> Optional[pv.PolyData]:
    parts = [pv.Box(bounds=b) for b in boxes if b[1] >= b[0] and b[3] >= b[2] and b[5] >= b[4]]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else parts[0].merge(parts[1:], merge_points=False)


class SceneAdapter:
    def __init__(self, plotter: pv.Plotter) -> None:
        self.pl = plotter
        self.pl.set_background(BACKGROUND)
        self._flat = False
        self.quality: dict = {}
        self.skybox_state = "none"
        self._owners: dict = {}                    # actor name -> (node, primitive), for click-picking
        self.selection = None                      # the PickInfo that is highlighted (kept across redraws)
        self.fast_volumes = False                  # True: smoke / fire use the software mapper (set when the GPU one is slow)

    # -- camera ------------------------------------------------------------------------------------
    def apply_camera(self, vp: vm.Viewpoint) -> None:
        cam = self.pl.camera
        cam.position, cam.focal_point, cam.up = tuple(vp.position), tuple(vp.target), tuple(vp.up)
        cam.view_angle = vp.fov_deg
        cam.parallel_projection = vp.projection == "orthogonal"
        if vp.projection == "orthogonal":
            dist = float(np.linalg.norm(np.subtract(vp.position, vp.target)))
            cam.parallel_scale = max(dist * np.tan(np.radians(vp.fov_deg / 2)), 1e-3)
        if vp.zoom != 1.0:
            cam.zoom(vp.zoom)

    def read_camera(self, base: vm.Viewpoint) -> vm.Viewpoint:
        """The camera as the user has moved it (so "Save viewpoint" / new keyframes record what they see)."""
        cam = self.pl.camera
        out = vm.Viewpoint(**{**base.__dict__})
        out.position, out.target, out.up = tuple(cam.position), tuple(cam.focal_point), tuple(cam.up)
        out.fov_deg, out.zoom = float(cam.view_angle), 1.0
        out.projection = "orthogonal" if cam.parallel_projection else "perspective"
        return out

    # -- drawing -------------------------------------------------------------------------------------
    def draw(self, frame, viz: vm.ResultsVisualization, camera: bool = False, decorations: bool = True) -> int:
        """Rebuild the scene. Returns the number of actors added. ``decorations=False`` leaves out the time overlay and the
        scalar bars (colours still follow the colorbars), as wanted for the six faces of a 360 picture."""
        pl = self.pl
        was = pl.suppress_rendering
        pl.suppress_rendering = True                   # every add_mesh would render the scene again: render once, at the end
        try:
            return self._draw(frame, viz, camera, decorations)
        finally:
            pl.suppress_rendering = was

    def _draw(self, frame, viz, camera: bool, decorations: bool) -> int:
        pl = self.pl
        pl.clear()
        pl.set_background(BACKGROUND)
        self.quality = apply_quality(pl, viz.rendering)
        self._flat = viz.rendering.slice_renderer == "compatibility"
        bars = {q: bar for q, _, bar in frame.colorbars}
        n = 0
        self._owners = {}
        for node, prim in frame.items:
            try:
                before = set(pl.renderer.actors)
                n += self._draw_one(node, prim, bars, viz)
                for name in set(pl.renderer.actors) - before:
                    self._owners[name] = (node, prim)
            except Exception as exc:                            # one bad primitive must not blank the view
                pl.add_text(f"{node.label}: {exc}", position="lower_left", font_size=7, name=f"err_{node.id}")
        n += self._annotations(viz)
        self._highlight()
        self.skybox_state = self._skybox(viz)
        if frame.overlay and decorations:
            pl.add_text(frame.overlay, position="upper_left", font_size=11, color="white", name="time_overlay")
        for q, units, bar in (frame.colorbars[:3] if decorations else []):
            self._scalar_bar(q, units, bar, frame.colorbars.index((q, units, bar)))
        if camera and frame.camera is not None:
            self.apply_camera(frame.camera)
        return n

    # -- picking -----------------------------------------------------------------------------------
    def pick(self, x: int, y: int):
        """What is under the display point (x, y), as a ``pick.PickInfo``; ``None`` when only the background is there."""
        from pyfds.api.viz import pick as pk
        import vtk
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.005)
        if not picker.Pick(float(x), float(y), 0.0, self.pl.renderer):
            return None
        actor = picker.GetActor()
        name = next((n for n, a in self.pl.renderer.actors.items() if a is actor), None)
        if name not in self._owners:
            return None
        node, prim = self._owners[name]
        label = node.label
        if label.startswith("Mesh") and "/" in node.id:            # "Mesh 1" alone says little: name the slice or quantity too
            label = f"{node.id.split('/')[-2]} / {label}"
        return pk.describe(node.id, label, prim, picker.GetPickPosition())

    def select(self, info) -> None:
        """Highlight the picked object (``None`` clears the highlight)."""
        self.selection = info
        self._highlight()

    def _highlight(self) -> None:
        pl = self.pl
        pl.remove_actor("pick_highlight", render=False)
        info = self.selection
        if info is None or info.box is None:
            return
        pl.add_mesh(pv.Box(bounds=info.box).extract_all_edges(), color="#ffe14d", line_width=3, name="pick_highlight",
                    pickable=False, render_lines_as_tubes=False)

    def _scalar_bar(self, q: str, units: str, bar, slot: int) -> None:
        a = pv.PolyData(np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]), faces=np.array([3, 0, 1, 2]))
        a["v"] = np.array([bar.lo, bar.hi, bar.lo])
        from matplotlib.colors import ListedColormap
        cmap = ListedColormap(bar.table()[:, :3])
        actor = self.pl.add_mesh(a, scalars="v", cmap=cmap, clim=(bar.lo, bar.hi), show_scalar_bar=True, opacity=0.0, name=f"bar_{slot}",
                                 scalar_bar_args=dict(title=f"{q}\n({units})", vertical=True, position_x=0.90 - 0.13 * slot,
                                                      position_y=0.15, height=0.7, width=0.07, n_labels=6,
                                                      title_font_size=9, label_font_size=9, color="white", fmt="%.4g"))
        actor.mapper.lookup_table = _lut(bar)
        actor.mapper.scalar_range = (bar.lo, bar.hi)

    def _draw_one(self, node, prim, bars: Dict[str, Any], viz: vm.ResultsVisualization) -> int:
        pl = self.pl
        mode = viz.rendering_mode
        wire = mode == "wireframe"
        if isinstance(prim, GeometryBoxes):
            mesh = _box_mesh(prim.boxes)
            if mesh is None:
                return 0
            if prim.kind == "mesh":                      # a computational mesh is only an outline, never a solid
                pl.add_mesh(mesh, color="#5c6b7a", style="wireframe", line_width=1, pickable=False, name=f"{node.id}#{prim.kind}")
                return 1
            if prim.kind == "open_vent":                 # the open sides of the domain: a faint outline, so the room stays visible
                pl.add_mesh(mesh, color="#c97b3a", style="wireframe", line_width=1, opacity=0.5, pickable=False,
                            name=f"{node.id}#{prim.kind}")
                return 1
            if prim.kind == "vent":
                pl.add_mesh(mesh, color="#c97b3a", style="wireframe" if wire else "surface", opacity=0.6, name=f"{node.id}#{prim.kind}")
                return 1
            pl.add_mesh(mesh, color="#9aa4b2", style="wireframe" if wire else "surface",
                        show_edges=mode.endswith("outlines") or wire, edge_color="#222222", opacity=1.0, name=f"{node.id}#{prim.kind}")
            return 1
        if isinstance(prim, ErrorBoxes):
            mesh = _box_mesh(prim.boxes)
            if mesh is not None:
                pl.add_mesh(mesh, color="red", style="wireframe", line_width=2, name=node.id)
                return 1
            return 0
        bar = bars.get(getattr(prim, "quantity", ""))
        if isinstance(prim, GridSurface):
            grid = pv.StructuredGrid(prim.x, prim.y, prim.z)
            grid["v"] = prim.values.ravel(order="F")
            self._add_scalar(grid, bar, node.id)
            return 1
        if isinstance(prim, TriMesh):
            if len(prim.faces) == 0:
                return 0
            mesh = pv.PolyData(prim.vertices, np.column_stack([np.full(len(prim.faces), 3), prim.faces]).ravel())
            if prim.values is not None and bar is not None:
                mesh["v"] = prim.values
                self._add_scalar(mesh, bar, node.id)
            else:
                pl.add_mesh(mesh, color="#e0b040", opacity=0.6, smooth_shading=True, name=node.id)
            return 1
        if isinstance(prim, PointCloud):
            cloud = pv.PolyData(prim.points)
            if prim.values is not None and bar is not None:
                cloud["v"] = prim.values
                actor = pl.add_mesh(cloud, scalars="v", point_size=max(prim.diameter, 3.0) if prim.diameter > 1 else 4.0,
                                    render_points_as_spheres=True, show_scalar_bar=False, name=node.id)
                actor.mapper.lookup_table = _lut(bar)
                actor.mapper.scalar_range = (bar.lo, bar.hi)
            else:
                pl.add_mesh(cloud, color="#6cc6ff", point_size=4.0, render_points_as_spheres=True, name=node.id)
            return 1
        if isinstance(prim, VectorField):
            if len(prim.points) == 0:
                return 0
            cloud = pv.PolyData(prim.points)
            cloud["vec"] = prim.vectors
            speed = np.linalg.norm(prim.vectors, axis=1)
            cloud["v"] = prim.values if prim.values is not None else speed
            scale = float(np.nanmax(speed)) or 1.0
            arrows = cloud.glyph(orient="vec", scale=False, factor=0.15 * max(viz.slice_vectors.get(node.quantity + "|" + node.label,
                                 vm.SliceVectorProps()).factor, 1e-6))
            if arrows.n_points:
                self._add_scalar(arrows, bar, node.id, array="v", fallback=cloud["v"])
            return 1
        if isinstance(prim, RectilinearVolume):
            return self._volume(node, prim, bar, viz)
        return 0

    def _add_scalar(self, mesh, bar, name: str, array: str = "v", fallback=None) -> None:
        if bar is None:
            self.pl.add_mesh(mesh, color="#c0c0c0", name=name)
            return
        if array not in mesh.array_names and fallback is not None:
            mesh[array] = np.resize(fallback, mesh.n_points)
        actor = self.pl.add_mesh(mesh, scalars=array, show_scalar_bar=False, nan_opacity=0.0, name=name,
                                 show_edges=False, interpolate_before_map=not self._flat)
        actor.mapper.lookup_table = _lut(bar)
        actor.mapper.scalar_range = (bar.lo, bar.hi)

    def _volume(self, node, vol: RectilinearVolume, bar, viz: vm.ResultsVisualization) -> int:
        grid = pv.RectilinearGrid(vol.x, vol.y, vol.z)
        sp = viz.smoke3d
        mapper = "fixed_point" if self.fast_volumes else volume_mapper(viz.rendering)
        compat = mapper == "fixed_point"
        if vol.kind == "smoke" and vol.extinction is not None:
            dx = vol.cell_size()
            alpha = (1.0 - np.exp(-vol.extinction * sp.smoke_opacity * sp.smoke_brightness * dx * 2.0))
            grid["a"] = np.clip(alpha, 0, 1).ravel(order="F")
            grid = self._uniform(grid, vol) if compat else grid
            self.pl.add_volume(grid, scalars="a", cmap="gray_r", opacity="linear", clim=(0, 1), show_scalar_bar=False,
                               name=node.id, shade=False, mapper=mapper)
            self._jitter(node.id, viz)
            return 1
        if vol.kind == "fire":
            grid["h"] = vol.values.ravel(order="F")
            hi = float(np.nanmax(vol.values)) or 1.0
            grid = self._uniform(grid, vol) if compat else grid
            self.pl.add_volume(grid, scalars="h", cmap="hot", opacity="linear", clim=(0, hi * sp.fire_brightness or hi),
                               show_scalar_bar=False, name=node.id, shade=False, mapper=mapper)
            self._jitter(node.id, viz)
            return 1
        # plain scalar volume: shown as its outline plus a mid-plane so something readable is there
        grid["v"] = vol.values.ravel(order="F")
        self.pl.add_mesh(grid.outline(), color="#777777", name=node.id + "/outline")
        if bar is not None:
            mid = grid.slice(normal="y", origin=[(vol.x[0] + vol.x[-1]) / 2, (vol.y[0] + vol.y[-1]) / 2, (vol.z[0] + vol.z[-1]) / 2])
            if mid.n_points:
                self._add_scalar(mid, bar, node.id, array="v")
        return 1

    @staticmethod
    def _uniform(grid, vol: RectilinearVolume):
        """The software volume mapper needs a uniform grid: resample at the finest cell size."""
        h = min(float(np.diff(a).min()) for a in (vol.x, vol.y, vol.z) if len(a) > 1)
        dims = [max(int(round((a[-1] - a[0]) / h)) + 1, 2) for a in (vol.x, vol.y, vol.z)]
        img = pv.ImageData(dimensions=dims, spacing=(h, h, h), origin=(vol.x[0], vol.y[0], vol.z[0]))
        return img.sample(grid)

    def _skybox(self, viz: vm.ResultsVisualization) -> str:
        """Draw the sky behind the model (View > Edit Skybox). Returns what was drawn, or why nothing was."""
        sb = viz.skybox
        pl = self.pl
        try:
            pl.remove_environment_texture()
        except Exception:
            pass
        if sb.kind == "none" or not sb.show:
            return "none"
        try:
            if sb.kind == "predefined":
                pl.set_background("#3b5f8f", top="#c4dcf2")
                return "gradient"
            tex = self._sky_texture(sb)
            pl.set_environment_texture(tex)
            r = pl.renderer
            if sb.z_rotation and hasattr(r, "SetEnvironmentRight"):
                import math
                a = math.radians(sb.z_rotation)
                r.SetEnvironmentRight(math.cos(a), math.sin(a), 0.0)
            if viz.rendering.image_based_lighting and hasattr(r, "SetUseImageBasedLighting"):
                r.SetUseImageBasedLighting(True)
            return "texture"
        except Exception as exc:
            pl.add_text(f"skybox: {exc}", position="lower_right", font_size=7, name="skybox_error")
            return f"error: {exc}"

    @staticmethod
    def _sky_texture(sb):
        import tempfile
        from pathlib import Path
        from pyfds.api.viz import panorama
        if sb.kind == "image360":
            return pv.read_texture(sb.files[0])
        if sb.kind == "split_cubemap":
            return pv.cubemap_from_filenames(list(sb.files))
        if sb.kind == "cubemap":
            from PIL import Image
            faces = panorama.cross_to_faces(np.asarray(Image.open(sb.files[0]).convert("RGB")))
            tmp = Path(tempfile.mkdtemp(prefix="skybox_"))
            names = []
            for f in ("+x", "-x", "+y", "-y", "+z", "-z"):
                q = tmp / (("p" if f[0] == "+" else "n") + f[1] + ".png")
                Image.fromarray(np.ascontiguousarray(faces[f])).save(q)
                names.append(str(q))
            return pv.cubemap_from_filenames(names)
        raise ValueError(f"unknown skybox type {sb.kind}")

    def _jitter(self, name: str, viz) -> None:
        """Reduce Banding: jitter the ray start so the layered look of volume rendering is broken up."""
        actor = self.pl.renderer.actors.get(name)
        mapper = getattr(actor, "mapper", None)
        for obj in (mapper, getattr(mapper, "_mapper", None)):
            if obj is not None and hasattr(obj, "SetUseJittering"):
                obj.SetUseJittering(bool(viz.rendering.reduce_banding))
                return

    def _annotations(self, viz: vm.ResultsVisualization) -> int:
        from pyfds.api.viz import annotations as an
        n = 0
        if viz.show_dimensions:
            for i, d in enumerate(viz.dimensions):
                try:
                    g = an.dimension_geometry(d, viz.general.dimension_precision)
                except ValueError:
                    continue
                lines = [g.start, g.end] + [p for e in g.extension for p in e]
                self.pl.add_lines(np.array([g.start, g.end]), color="yellow", width=2, name=f"dim_{i}")
                self.pl.add_point_labels([g.text_at], [g.text], font_size=12, text_color="yellow", shape=None,
                                         show_points=False, name=f"dimt_{i}")
                n += 2
        if viz.show_labels:
            for i, lab in enumerate(viz.labels):
                at = lab.position or lab.anchor
                self.pl.add_point_labels([at], [lab.text], font_size=12, text_color="white", shape_color="#333333",
                                         show_points=lab.position is None, name=f"lab_{i}")
                if lab.position is not None:
                    self.pl.add_lines(np.array([lab.anchor, lab.position]), color="white", width=1, name=f"labl_{i}")
                n += 1
        return n


def _blur_times(viewer, t: float, samples: int = 5):
    """Shutter times for motion blur: *samples* times spread over ``viewer.motion_blur_span`` centred on *t*."""
    span = getattr(viewer, "motion_blur_span", 0.0)
    if not viewer.viz.motion_blur or span <= 0:
        return [t]
    return [t + span * (k / (samples - 1) - 0.5) for k in range(samples)]


def _camera_for(viewer, fr, t: float, view: str):
    from pyfds.api.viz import capture as cap
    from pyfds.api.viz import views as vw
    if view in (cap.CURRENT, "Default"):
        return fr.camera or viewer.viz.camera
    v = viewer.viz.view(view)
    return vw.camera_at(v.tour, t) if v.tour and v.tour.keyframes else (v.viewpoint or viewer.viz.camera)


def _shot(viewer, size, t: float, view: str) -> np.ndarray:
    pl = pv.Plotter(off_screen=True, window_size=tuple(size))
    try:
        ad = SceneAdapter(pl)
        fr = viewer.frame(t)
        ad.draw(fr, viewer.viz, camera=False)
        ad.apply_camera(_camera_for(viewer, fr, t, view))
        return pl.screenshot(return_img=True)
    finally:
        pl.close()


def _save(path: str, img: np.ndarray) -> None:
    from PIL import Image
    Image.fromarray(np.ascontiguousarray(img[..., :3] if img.ndim == 3 else img)).save(path)


def _averaged(images) -> np.ndarray:
    acc = None
    n = 0
    for img in images:
        a = img.astype(np.float32)
        acc = a if acc is None else acc + a
        n += 1
    return (acc / n).round().astype(np.uint8)


def make_offscreen_renderer(viewer):
    """``renderer(path, size, time, view)`` for ``api.viewer.render_screenshots`` / ``render_movie``: draws on a
    separate off-screen plotter, so a live window's camera is not disturbed (and no window is needed at all). With
    motion blur on, a movie frame is the average of several shutter times (``viewer.motion_blur_span``)."""
    def render(path: str, size, t: float, view: str) -> None:
        _save(path, _averaged(_shot(viewer, size, tt, view) for tt in _blur_times(viewer, t)))

    return render


def render_cube_faces(viewer, t: float, face_size: int, view: str = "<current view>") -> dict:
    """The six 90 degree views from the camera position of *view* at *t* (no overlay, no colorbars)."""
    from pyfds.api.viz import panorama
    fr = viewer.frame(t)
    cam = _camera_for(viewer, fr, t, view)
    pl = pv.Plotter(off_screen=True, window_size=(face_size, face_size))
    faces = {}
    try:
        ad = SceneAdapter(pl)
        ad.draw(fr, viewer.viz, camera=False, decorations=False)
        for name in panorama.ORDER:
            pos, focal, up = panorama.face_camera(name, cam.position)
            c = pl.camera
            c.position, c.focal_point, c.up = pos, focal, up
            c.view_angle = 90.0
            c.parallel_projection = False
            pl.camera_set = True                       # otherwise the first render resets the camera to fit the scene
            pl.reset_camera_clipping_range()
            pl.render()                                # screenshot() renders only the first time
            faces[name] = pl.screenshot(return_img=True)[..., :3].copy()          # the buffer is reused by the next render
    finally:
        pl.close()
    return faces


def make_panorama_renderer(viewer):
    """Like :func:`make_offscreen_renderer` but every frame is a 360 degree equirectangular picture of *size*."""
    from pyfds.api.viz import panorama

    def one(t: float, w: int, h: int, view: str) -> np.ndarray:
        return panorama.equirect(render_cube_faces(viewer, t, max(w // 4, 16), view), w, h)

    def render(path: str, size, t: float, view: str) -> None:
        w, h = size
        _save(path, _averaged(one(tt, w, h, view) for tt in _blur_times(viewer, t)))

    return render
