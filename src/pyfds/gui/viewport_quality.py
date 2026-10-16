"""Picture and quality methods of the 3D viewport: graphics-card info, anti-aliasing, and getting the view as an image
(snapshot to a file, QImage for printing). Mixed into ``Viewport3D``; needs ``self.plotter``."""
from __future__ import annotations


class ViewportQualityMixin:
    # ── Graphics hardware and quality ────────────────────────────────────────

    def opengl_info(self) -> dict:
        """Vendor, renderer and OpenGL version of the context the 3D view runs on."""
        info = {}
        for line in self.plotter.render_window.ReportCapabilities().splitlines()[:6]:
            for key, label in (("vendor", "OpenGL vendor string:"), ("renderer", "OpenGL renderer string:"),
                               ("version", "OpenGL version string:")):
                if line.startswith(label):
                    info[key] = line[len(label):].strip()
        return info

    def set_antialiasing(self, mode: str) -> None:
        """off, fxaa, msaa4 or msaa8 (smoother edges; the higher ones cost more on a weak graphics card)."""
        if mode == "off":
            self.plotter.disable_anti_aliasing()
        elif mode == "fxaa":
            self.plotter.enable_anti_aliasing("fxaa")
        elif mode in ("msaa4", "msaa8"):
            self.plotter.enable_anti_aliasing("msaa", multi_samples=int(mode[-1]))
        else:
            raise ValueError("anti-aliasing must be off, fxaa, msaa4 or msaa8")
        self.plotter.render()

    def image(self):
        """The current view as a QImage (for printing)."""
        import numpy as np
        from PySide6.QtGui import QImage
        arr = np.ascontiguousarray(self.plotter.screenshot(None))
        h, w = arr.shape[:2]
        return QImage(arr.data, w, h, 3 * w, QImage.Format_RGB888).copy()

    # ── Snapshot (UX-15) ─────────────────────────────────────────────────────

    def snapshot(self, path: str, scale: int = 1) -> str:
        """Save the current view as an image (PNG/JPG by extension); *scale* 2 doubles the resolution."""
        self.plotter.screenshot(path, scale=max(1, int(scale)))
        return path
