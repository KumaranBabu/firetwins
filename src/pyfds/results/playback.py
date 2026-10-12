"""Playback and camera for the results scene (RES-02, RES-10): pure state, no timers, no drawing.

``Playback`` is a small state machine the view drives: call ``tick(dt)`` from a timer with the wall-clock
seconds since the last call and draw when it returns True. ``CameraPath`` interpolates keyframed cameras
over simulation time; ``SavedViews`` keeps named cameras. Both serialise to plain dicts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from pyfds.core.viewport import ProjectionMode, ViewportCamera


class Playback:
    """Play / pause / step / loop / speed / seek over a list of frame times."""

    def __init__(self, times: Sequence[float]) -> None:
        self.times = np.asarray(times, dtype=float)
        if len(self.times) == 0:
            raise ValueError("nothing to play: the scene has no frames")
        if np.any(np.diff(self.times) <= 0):
            raise ValueError("frame times must increase")
        self.index = 0
        self.time = float(self.times[0])
        self.playing = False
        self.loop = False
        self.speed = 1.0                # simulated seconds per wall-clock second

    @property
    def n_frames(self) -> int:
        return len(self.times)

    @property
    def progress(self) -> float:
        span = self.times[-1] - self.times[0]
        return 0.0 if span == 0 else float((self.time - self.times[0]) / span)

    @property
    def at_end(self) -> bool:
        return self.index >= self.n_frames - 1

    # transport
    def play(self) -> None:
        if self.at_end and not self.loop:           # play from the end restarts
            self.seek_index(0)
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def toggle(self) -> bool:
        (self.pause if self.playing else self.play)()
        return self.playing

    def set_speed(self, speed: float) -> None:
        if not speed > 0:
            raise ValueError("speed must be positive")
        self.speed = float(speed)

    def set_loop(self, loop: bool) -> None:
        self.loop = bool(loop)

    # position
    def _set(self, index: int) -> bool:
        changed = index != self.index
        self.index = index
        return changed

    def seek_index(self, i: int) -> int:
        if not -self.n_frames <= i < self.n_frames:
            raise IndexError(f"frame {i} out of range (0..{self.n_frames - 1})")
        i %= self.n_frames
        self.time = float(self.times[i])
        self.index = i
        return i

    def seek_time(self, t: float) -> int:
        """Jump to the last frame at or before *t* (clamped to the timeline)."""
        t = float(np.clip(t, self.times[0], self.times[-1]))
        self.index = int(np.clip(np.searchsorted(self.times, t + 1e-9) - 1, 0, self.n_frames - 1))
        self.time = t
        return self.index

    def seek_progress(self, fraction: float) -> int:
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("fraction must be between 0 and 1")
        return self.seek_time(self.times[0] + fraction * (self.times[-1] - self.times[0]))

    def step(self, n: int = 1) -> int:
        """Move *n* frames (negative = back), stopping playback; clamps at both ends."""
        self.playing = False
        return self.seek_index(int(np.clip(self.index + n, 0, self.n_frames - 1)))

    # clock
    def tick(self, dt: float) -> bool:
        """Advance by *dt* wall-clock seconds; True when the frame changed (time moves continuously)."""
        if dt < 0:
            raise ValueError("dt must not be negative")
        if not self.playing:
            return False
        before = self.index
        t = self.time + dt * self.speed
        if t > self.times[-1]:
            if self.loop:
                span = self.times[-1] - self.times[0]
                t = self.times[0] + ((t - self.times[0]) % span if span else 0.0)
            else:
                t = float(self.times[-1])
                self.playing = False
        self.seek_time(t)
        return self.index != before or not self.playing


def _cam_from_dict(d: Dict[str, Any]) -> ViewportCamera:
    proj = ProjectionMode[d.get("projection", "PERSPECTIVE")]
    return ViewportCamera(position=tuple(d["position"]), target=tuple(d["target"]), up=tuple(d.get("up", (0, 0, 1))),
                          fov_deg=d.get("fov_deg", 45.0), near=d.get("near", 0.01), far=d.get("far", 10_000.0),
                          zoom=d.get("zoom", 1.0), projection=proj)


def _lerp(a: Sequence[float], b: Sequence[float], u: float) -> Tuple[float, ...]:
    return tuple(float(x + (y - x) * u) for x, y in zip(a, b))


def interpolate(a: ViewportCamera, b: ViewportCamera, u: float) -> ViewportCamera:
    return ViewportCamera(position=_lerp(a.position, b.position, u), target=_lerp(a.target, b.target, u),
                          up=_lerp(a.up, b.up, u), fov_deg=a.fov_deg + (b.fov_deg - a.fov_deg) * u,
                          near=a.near, far=a.far, zoom=a.zoom + (b.zoom - a.zoom) * u, projection=a.projection)


class CameraPath:
    """Keyframed fly-through over simulation time (cameras before the first / after the last key hold still)."""

    def __init__(self, smooth: bool = True) -> None:
        self._keys: List[Tuple[float, ViewportCamera]] = []
        self.smooth = smooth

    @property
    def keys(self) -> List[Tuple[float, ViewportCamera]]:
        return list(self._keys)

    def add_key(self, t: float, camera: ViewportCamera) -> None:
        """Add (or replace the key at the same time)."""
        self._keys = [k for k in self._keys if abs(k[0] - t) > 1e-9] + [(float(t), camera)]
        self._keys.sort(key=lambda k: k[0])

    def remove_key(self, t: float) -> None:
        n = len(self._keys)
        self._keys = [k for k in self._keys if abs(k[0] - t) > 1e-9]
        if len(self._keys) == n:
            raise KeyError(f"no key at t={t}")

    def at(self, t: float) -> ViewportCamera:
        if not self._keys:
            raise ValueError("the camera path has no keys")
        ts = [k[0] for k in self._keys]
        if t <= ts[0]:
            return self._keys[0][1]
        if t >= ts[-1]:
            return self._keys[-1][1]
        j = int(np.searchsorted(ts, t, side="right"))
        (t0, c0), (t1, c1) = self._keys[j - 1], self._keys[j]
        u = (t - t0) / (t1 - t0)
        if self.smooth:
            u = u * u * (3 - 2 * u)                        # smoothstep: ease in and out of each key
        return interpolate(c0, c1, u)

    def to_dict(self) -> Dict[str, Any]:
        return {"smooth": self.smooth, "keys": [{"t": t, "camera": c.to_dict()} for t, c in self._keys]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CameraPath":
        p = cls(d.get("smooth", True))
        for k in d.get("keys", []):
            p.add_key(k["t"], _cam_from_dict(k["camera"]))
        return p


class SavedViews:
    """Named cameras."""

    def __init__(self) -> None:
        self._views: Dict[str, ViewportCamera] = {}

    def save(self, name: str, camera: ViewportCamera, overwrite: bool = False) -> None:
        if not name.strip():
            raise ValueError("a view needs a name")
        if name in self._views and not overwrite:
            raise ValueError(f"a view called {name!r} already exists")
        self._views[name] = camera

    def get(self, name: str) -> ViewportCamera:
        try:
            return self._views[name]
        except KeyError:
            raise KeyError(f"no saved view {name!r}; have {sorted(self._views)}") from None

    def delete(self, name: str) -> None:
        self.get(name)
        del self._views[name]

    def names(self) -> List[str]:
        return sorted(self._views)

    def to_dict(self) -> Dict[str, Any]:
        return {n: c.to_dict() for n, c in self._views.items()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SavedViews":
        v = cls()
        for n, c in d.items():
            v._views[n] = _cam_from_dict(c)
        return v
