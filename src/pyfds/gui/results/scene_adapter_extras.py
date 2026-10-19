"""SceneAdapter: skybox, jitter and annotations."""
from __future__ import annotations

import numpy as np
import pyvista as pv

from pyfds.api.viz import model as vm


class SceneAdapterExtrasMixin:
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
                self.pl.add_lines(np.array([g.start, g.end]), color="yellow", width=2, name=f"dim_{i}")
                for j, (e0, e1) in enumerate(g.extension):                       # the two extension lines from the measured points
                    self.pl.add_lines(np.array([e0, e1]), color="yellow", width=1, name=f"dimx_{i}_{j}")
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
