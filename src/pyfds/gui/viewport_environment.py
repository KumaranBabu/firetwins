"""Lighting for the 3D viewport (plan step F2): the standard light kit, and a procedural sky-and-ground environment that
the *Realistic* render mode reflects in metallic materials (physically based shading has nothing to reflect without it,
so metals would draw almost black). No image files: the environment is generated from a colour gradient."""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pyvista as pv

_ZENITH = np.array([0.50, 0.66, 0.95])
_HORIZON = np.array([0.93, 0.94, 0.96])
_GROUND = np.array([0.30, 0.30, 0.32])


def _gradient(size: int, v: np.ndarray) -> np.ndarray:
    """RGB rows for heights v in [-1 (down), +1 (up)]: ground -> horizon -> zenith."""
    t = np.clip(v, -1.0, 1.0)[:, None]
    up = _HORIZON + (_ZENITH - _HORIZON) * np.clip(t, 0, 1)
    down = _HORIZON + (_GROUND - _HORIZON) * np.clip(-t * 3.0, 0, 1)
    return np.where(t >= 0, up, down)


def _face(size: int, kind: str) -> pv.ImageData:
    """One cube face. ``side`` faces run from ground (bottom) to zenith (top); ``top`` / ``bottom`` are flat."""
    if kind == "top":
        rgb = np.tile(_ZENITH, (size * size, 1))
    elif kind == "bottom":
        rgb = np.tile(_GROUND, (size * size, 1))
    else:
        rows = _gradient(size, np.linspace(-1.0, 1.0, size))             # row 0 is the bottom of the image
        rgb = np.repeat(rows[:, None, :], size, axis=1).reshape(-1, 3)
    img = pv.ImageData(dimensions=(size, size, 1))
    img.point_data["Image"] = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    return img


def sky_cubemap(size: int = 32) -> pv.Texture:
    """A cube map with a bright sky above, a horizon band and a darker ground (faces +X -X +Y -Y +Z -Z; +Y is up
    in the map; ``Environment.apply`` tells the renderer that the model's up is +Z)."""
    kinds = ["side", "side", "top", "bottom", "side", "side"]
    return pv.Texture([_face(size, k) for k in kinds])


def set_lights(plotter: Any) -> None:
    """The standard three-point light kit. ``plotter.clear()`` removes every light, and a scene without lights is drawn
    flat, so the viewport calls this after each rebuild."""
    plotter.remove_all_lights()
    plotter.enable_lightkit()


class Environment:
    """Owns the generated cube map and switches it on for the realistic render mode."""

    def __init__(self) -> None:
        self._texture: Optional[pv.Texture] = None

    def apply(self, plotter: Any, realistic: bool) -> None:
        if not realistic:
            plotter.remove_environment_texture()
            return
        if self._texture is None:
            self._texture = sky_cubemap()
        plotter.set_environment_texture(self._texture, is_srgb=True, show_background=False)
        plotter.renderer.SetEnvironmentUp(0.0, 0.0, 1.0)         # the model is Z-up
        plotter.renderer.SetEnvironmentRight(1.0, 0.0, 0.0)
