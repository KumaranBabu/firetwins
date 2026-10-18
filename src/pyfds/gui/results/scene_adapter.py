"""Draws an ``api.viewer`` :class:`Frame` into a PyVista plotter.

Only this module (and the window) know about VTK; everything it draws comes from the data layer. It works
on any ``pyvista.Plotter`` - a ``QtInteractor`` in the window, an off-screen plotter for screenshots, movies
and tests. Each ``draw`` clears and rebuilds the actors (cheap for the sizes involved) and keeps the camera
unless asked to apply one.
"""
from __future__ import annotations

import numpy as np
import pyvista as pv

from pyfds.api.viz import model as vm
from .quality import apply_quality

from .scene_adapter_common import (  # noqa: F401  (re-exported)
    BACKGROUND,
    _box_mesh,
    _lut,
)
from .scene_adapter_extras import (  # noqa: F401  (re-exported)
    SceneAdapterExtrasMixin,
)
from .scene_adapter_items import (  # noqa: F401  (re-exported)
    SceneAdapterItemsMixin,
)

from .scene_adapter_common import (  # noqa: F401  (re-exported)
    _box_mesh,
)


class SceneAdapter(SceneAdapterItemsMixin, SceneAdapterExtrasMixin):
    def __init__(self, plotter: pv.Plotter) -> None:
        self.pl = plotter
        self.pl.set_background(BACKGROUND)
        self._flat = False
        self.quality: dict = {}
        self.skybox_state = "none"
        self._owners: dict = {}                    # actor name -> (node, primitive), for click-picking
        self.selection = None                      # the PickInfo that is highlighted (kept across redraws)
        self.selections: list = []                 # every highlighted PickInfo (Ctrl / Alt click adds one)
        self._n_highlights = 0
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

    def select(self, info, add: bool = False) -> None:
        """Highlight the picked object (``None`` clears the highlight). With *add* the object joins the ones already
        highlighted, or leaves them if it was already one of them."""
        if info is None:
            self.selections = []
        elif add:
            same = [i for i in self.selections if i.node_id == info.node_id and i.text == info.text]
            self.selections = [i for i in self.selections if i not in same] if same else self.selections + [info]
        else:
            self.selections = [info]
        self.selection = self.selections[-1] if self.selections else None
        self._highlight()

    def _highlight(self) -> None:
        pl = self.pl
        for k in range(max(self._n_highlights, 1)):
            pl.remove_actor("pick_highlight" if k == 0 else f"pick_highlight_{k}", render=False)
        shown = [i for i in self.selections if i.box is not None]
        if not self.selections and self.selection is not None:          # set directly (a restored selection)
            shown = [self.selection] if self.selection.box is not None else []
        for k, info in enumerate(shown):
            pl.add_mesh(pv.Box(bounds=info.box).extract_all_edges(), color="#ffe14d", line_width=3,
                        name="pick_highlight" if k == 0 else f"pick_highlight_{k}", pickable=False,
                        render_lines_as_tubes=False)
        self._n_highlights = len(shown)

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
