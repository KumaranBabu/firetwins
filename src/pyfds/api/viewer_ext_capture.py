"""ViewerExtras: screenshots, movies and encoding."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pyfds.results.viz import capture as cap

from .viewer_ext_common import Renderer


class ViewerExtrasCaptureMixin:
    def screenshot_plan(self, path: str, mode: str = "single", time: Optional[float] = None, view: str = cap.CURRENT,
                        start: Optional[float] = None, end: Optional[float] = None, interval: float = 1.0,
                        views: Sequence[str] = (cap.CURRENT,), tsv: Optional[str] = None) -> List[cap.Shot]:
        lo, hi = self.time_range()
        if mode == "single":
            return cap.single(path, self.time if time is None else time, view)
        if mode == "multiple":
            return cap.multiple(path, lo if start is None else start, hi if end is None else end, interval, views,
                                self._tour_ranges())
        if mode == "file":
            if not tsv:
                raise ValueError("file mode needs a .tsv file")
            return cap.from_file(path, Path(tsv).read_text(encoding="utf-8"), self._tour_ranges())
        raise ValueError("mode must be single, multiple or file")

    def screenshot(self, path: str, time: Optional[float] = None, view: str = cap.CURRENT,
                   size: Tuple[int, int] = (1280, 720)) -> str:
        """One image of the current scene (needs a renderer: open the results window or use the command line)."""
        if self.renderer is None:
            raise RuntimeError("no renderer is attached: open the results window (or run pyfds.gui.results.cli) first")
        return self.render_screenshots(self.screenshot_plan(path, "single", time, view), self.renderer, size)[0]

    def render_screenshots(self, shots: Sequence[cap.Shot], renderer: Renderer, size: Tuple[int, int] = (1920, 1080)) -> List[str]:
        """Draw each planned image with *renderer* (the 3D window's off-screen drawing)."""
        if size[0] < 16 or size[1] < 16:
            raise ValueError("the screenshot size is too small")
        views = {v.name for v in self.viz.views} | {cap.CURRENT, "Default"}
        out = []
        for s in shots:
            if s.view not in views:
                raise KeyError(f"no view called {s.view!r}")
            Path(s.path).parent.mkdir(parents=True, exist_ok=True)
            renderer(s.path, size, s.time, s.view)
            out.append(s.path)
        return out

    def render_movie(self, plan: cap.MoviePlan, renderer: Renderer, view: str = cap.CURRENT,
                     keep_frames: bool = False) -> Dict[str, Any]:
        """Render every frame and join them into the movie (MP4 through the bundled ffmpeg when available).

        Returns ``{"path", "frames", "encoded", "frames_dir"}``; ``encoded`` is False (and the PNG frames are kept
        beside the movie) when no encoder is available."""
        out = Path(plan.path)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=out.stem + "_frames_", dir=str(out.parent)))
        self.motion_blur_span = 0.5 * plan.speed / plan.fps if self.viz.motion_blur else 0.0     # half-frame shutter
        try:
            for i, t in enumerate(plan.times):
                renderer(cap.frame_path(str(tmp), out.stem, i), plan.size, t, view)
            rc = self.encode_frames(str(tmp), out.stem, str(out), plan.fps)
            encoded = rc == 0
            keep = keep_frames or not encoded
            if keep:
                keep_dir = out.parent / f"{out.stem}_frames"
                shutil.rmtree(keep_dir, ignore_errors=True)
                shutil.move(str(tmp), str(keep_dir))
                return {"path": str(out), "frames": len(plan.times), "encoded": encoded, "frames_dir": str(keep_dir)}
            return {"path": str(out), "frames": len(plan.times), "encoded": True, "frames_dir": None}
        finally:
            self.motion_blur_span = 0.0
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def encoder_path() -> Optional[str]:
        """An ffmpeg to join frames: the bundled one (``imageio-ffmpeg``) or one on the PATH."""
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return shutil.which("ffmpeg")

    def encode_frames(self, frames_dir: str, stem: str, output: str, fps: int = 30, bitrate_kbps: int = 6000) -> int:
        """Join ``stem_00000.png ...`` into an MP4. Returns 0 on success, 127 when no encoder is available."""
        ff = self.encoder_path()
        if ff is None:
            return 127
        cmd = [ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(Path(frames_dir) / f"{stem}_%05d.png"),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", f"{bitrate_kbps}k", str(output)]
        return subprocess.run(cmd, capture_output=True, text=True).returncode
