"""Preferences ▸ Rendering applied to a PyVista plotter (V11).

Which options really change what is drawn, and which are kept only so a visualization round-trips:

* applied here: antialiasing, ambient occlusion, smoke renderer (hardware GPU volume mapper / compatibility = software
  mapper), reduce banding (volume jitter), slice and Data3D renderers "compatibility" (flat cell colours, no smoothing);
* applied in ``api.viewer``: "disabled" Data3D renderers, level of detail, asynchronous frame loading;
* stored only (no VTK equivalent in this renderer): anisotropic filtering, vertex buffers, image based lighting,
  advanced lighting, the "smokeview" smoke renderer (drawn like hardware).
"""
from __future__ import annotations

from typing import Dict

APPLIED = {
    "antialiasing": "renderer", "ambient_occlusion": "renderer", "smoke_renderer": "renderer", "reduce_banding": "renderer",
    "slice_renderer": "renderer", "data3d_slice_renderer": "viewer", "data3d_renderer": "viewer", "level_of_detail": "viewer",
    "async_frames": "viewer", "anisotropic_filtering": "stored only", "vertex_buffers": "stored only",
    "image_based_lighting": "stored only", "advanced_lighting": "stored only",
}

NOTE = ("Applied by the 3D view: antialiasing, ambient occlusion, smoke / slice renderer, reduce banding, level of detail, "
        "asynchronous frame loading and the Data3D 'disabled' choices. Stored but without effect: anisotropic filtering, "
        "vertex buffers, image based lighting, advanced lighting.")


def apply_quality(plotter, prefs) -> Dict[str, str]:
    """Set antialiasing and ambient occlusion on *plotter*. Returns what was done (for tests and the status bar);
    options the graphics driver rejects are reported as ``"unsupported"`` rather than raising."""
    done: Dict[str, str] = {}
    aa = prefs.antialiasing
    try:
        plotter.disable_anti_aliasing()
        if aa.startswith("msaa"):
            plotter.enable_anti_aliasing("msaa", multi_samples=int(aa.split("_")[1]))
            done["antialiasing"] = aa
        elif aa.startswith("smaa"):
            plotter.enable_anti_aliasing("fxaa")                 # closest post-process filter VTK offers
            done["antialiasing"] = "fxaa"
        else:
            done["antialiasing"] = "disabled"
    except Exception:
        done["antialiasing"] = "unsupported"
    try:
        if prefs.ambient_occlusion:
            plotter.enable_ssao()
            done["ambient_occlusion"] = "ssao"
        else:
            plotter.disable_ssao()
            done["ambient_occlusion"] = "off"
    except Exception:
        done["ambient_occlusion"] = "unsupported"
    return done


def volume_mapper(prefs) -> str:
    return "fixed_point" if prefs.smoke_renderer == "compatibility" else "smart"
