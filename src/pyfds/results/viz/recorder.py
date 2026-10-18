"""Real-time movie recording (PyroSim Results Record / Pause / Resume / Stop, row V-68).

``LiveRecorder`` is fed images of the live 3D view at whatever pace the window manages. It keeps the film in real
time: it counts the seconds that were recorded (pauses do not count) and writes each image as many times as the
frame rate needs, so a slow redraw gives repeated frames, not a film that runs fast. Frames are piped to ffmpeg
(the bundled ``imageio-ffmpeg`` or one on the PATH); without an encoder they are kept as numbered PNG files.
Pure Python plus numpy: no Qt, no PyVista.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np

IDLE, RECORDING, PAUSED, STOPPED = "idle", "recording", "paused", "stopped"


def encoder_path() -> Optional[str]:
    """The bundled ffmpeg, else one on the PATH, else None."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


class LiveRecorder:
    def __init__(self, path: str, fps: int = 15, bitrate_kbps: int = 6000,
                 clock: Callable[[], float] = time.monotonic, ffmpeg: Optional[str] = "auto") -> None:
        if fps < 1:
            raise ValueError("the frame rate must be at least 1")
        self.path = str(path)
        self.fps = int(fps)
        self.bitrate_kbps = bitrate_kbps
        self._clock = clock
        self._ffmpeg = encoder_path() if ffmpeg == "auto" else ffmpeg      # "auto" finds one; None means no encoder (PNG frames)
        self.state = IDLE
        self.frames = 0                          # frames written so far
        self.size: Optional[tuple] = None        # (width, height) of the film, fixed by the first image
        self._proc: Optional[subprocess.Popen] = None
        self._frames_dir: Optional[Path] = None
        self._recorded = 0.0                     # seconds recorded before the current running stretch
        self._since: Optional[float] = None      # clock value when the current running stretch began

    # -- state -------------------------------------------------------------------------------------------------
    @property
    def elapsed(self) -> float:
        """Seconds of film so far (paused time is not counted)."""
        running = (self._clock() - self._since) if (self.state == RECORDING and self._since is not None) else 0.0
        return self._recorded + running

    def start(self) -> None:
        if self.state != IDLE:
            raise RuntimeError(f"cannot start a recording that is {self.state}")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.state, self._since = RECORDING, self._clock()

    def pause(self) -> None:
        if self.state != RECORDING:
            raise RuntimeError("nothing is being recorded")
        self._recorded += self._clock() - self._since
        self.state, self._since = PAUSED, None

    def resume(self) -> None:
        if self.state != PAUSED:
            raise RuntimeError("the recording is not paused")
        self.state, self._since = RECORDING, self._clock()

    # -- frames ------------------------------------------------------------------------------------------------
    def add_frame(self, image: np.ndarray) -> int:
        """Offer the current picture of the view (height x width x 3 or 4, uint8). Returns how many film frames it filled
        (0 while paused, or when the film is already ahead of the clock)."""
        if self.state != RECORDING:
            return 0
        img = self._normalise(image)
        due = int(self.elapsed * self.fps + 1e-6) + 1          # the first image is frame 0, at time 0
        n = max(0, due - self.frames)
        for _ in range(n):
            self._write(img)
        return n

    def _normalise(self, image: np.ndarray) -> np.ndarray:
        img = np.asarray(image)
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[..., :3]
        if img.ndim != 3 or img.shape[2] != 3:
            raise ValueError("a frame must be a height x width x 3 (or 4) image")
        h, w = img.shape[:2]
        if self.size is None:
            self.size = (w - w % 2, h - h % 2)           # H.264 needs even sides
        tw, th = self.size
        if (w, h) != (tw, th):
            if w >= tw and h >= th:
                img = img[:th, :tw]                      # the window was resized: crop or pad to the film's size
            else:
                pad = np.zeros((th, tw, 3), dtype=np.uint8)
                pad[:min(h, th), :min(w, tw)] = img[:th, :tw]
                img = pad
        return np.ascontiguousarray(img, dtype=np.uint8)

    def _write(self, img: np.ndarray) -> None:
        if self._ffmpeg is not None:
            if self._proc is None:
                w, h = self.size
                cmd = [self._ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                       "-framerate", str(self.fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                       "-b:v", f"{self.bitrate_kbps}k", self.path]
                self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            self._proc.stdin.write(img.tobytes())
        else:
            from PIL import Image
            if self._frames_dir is None:
                out = Path(self.path)
                self._frames_dir = out.parent / f"{out.stem}_frames"
                shutil.rmtree(self._frames_dir, ignore_errors=True)
                self._frames_dir.mkdir(parents=True)
            Image.fromarray(img).save(self._frames_dir / f"{Path(self.path).stem}_{self.frames:05d}.png")
        self.frames += 1

    # -- finishing ---------------------------------------------------------------------------------------------
    def stop(self) -> Dict[str, Any]:
        """Finish the film. Returns ``{"path", "frames", "seconds", "encoded", "frames_dir"}``."""
        if self.state in (IDLE, STOPPED):
            raise RuntimeError("nothing is being recorded")
        seconds = self.elapsed
        self.state, self._since = STOPPED, None
        encoded, error = self._ffmpeg is not None and self.frames > 0, ""
        if self._proc is not None:
            self._proc.stdin.close()
            error = self._proc.stderr.read().decode(errors="replace")
            encoded = self._proc.wait() == 0
            self._proc = None
            if not encoded:
                raise RuntimeError(f"ffmpeg could not write the movie: {error.strip()}")
        return {"path": self.path, "frames": self.frames, "seconds": round(seconds, 2), "encoded": encoded,
                "frames_dir": str(self._frames_dir) if self._frames_dir else None}

    def abort(self) -> None:
        """Drop an unfinished recording (window closed): the encoder is ended and the partial file kept."""
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=10)
            except Exception:
                self._proc.kill()
            self._proc = None
        self.state = STOPPED
