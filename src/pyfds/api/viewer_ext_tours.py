"""ViewerExtras: tours and keyframes."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from pyfds.results.viz import model as vm
from pyfds.results.viz import views as vw


class ViewerExtrasToursMixin:
    def _tour(self, view: Optional[str]) -> vm.Tour:
        v = self.viz.view(view or self.viz.active_view or "")
        if v.tour is None:
            raise ValueError(f"view {v.name!r} has no tour")
        if v.origin != "pyfds":
            raise ValueError("views from FDS or Smokeview cannot be edited; duplicate the view first")
        return v.tour

    def add_keyframe(self, time: Optional[float] = None, view: Optional[str] = None, transition: str = "move_to_next") -> vm.Keyframe:
        """Tour Editor ▸ Add: record the current camera at *time* (default the playback time)."""
        k = vw.add_keyframe(self._tour(view), self.time if time is None else time, self.viz.camera, transition)
        self.dirty = True
        return k

    def set_keyframe(self, index: int, view: Optional[str] = None, time: Optional[float] = None,
                     transition: Optional[str] = None, record_camera: bool = False) -> None:
        t = self._tour(view)
        k = t.keyframes[index]
        if transition is not None:
            if transition not in ("move_to_next", "stationary"):
                raise ValueError("transition must be move_to_next or stationary")
            k.transition = transition
        if record_camera:
            vw.record_camera(t, index, self.viz.camera)
        if time is not None:
            vw.shift_keyframes(t, [index], new_time=time)
        self.dirty = True

    def remove_keyframes(self, indices: Sequence[int], view: Optional[str] = None) -> None:
        vw.remove_keyframes(self._tour(view), indices)
        self.dirty = True

    def shift_keyframes(self, indices: Sequence[int], new_time: Optional[float] = None, offset: Optional[float] = None,
                        view: Optional[str] = None) -> None:
        vw.shift_keyframes(self._tour(view), indices, new_time, offset)
        self.dirty = True

    def duplicate_keyframes(self, indices: Sequence[int], mode: str = "end_of_tour", at_time: Optional[float] = None,
                            last_delay: float = 0.0, view: Optional[str] = None) -> List[vm.Keyframe]:
        out = vw.duplicate_keyframes(self._tour(view), indices, mode, at_time, last_delay)
        self.dirty = True
        return out

    def set_tour(self, view: Optional[str] = None, repeat: Optional[bool] = None, repeat_delay: Optional[float] = None) -> vm.Tour:
        t = self._tour(view)
        if repeat is not None:
            t.repeat = bool(repeat)
        if repeat_delay is not None:
            if repeat_delay < 0:
                raise ValueError("repeat delay must not be negative")
            t.repeat_delay = float(repeat_delay)
        self.dirty = True
        return t

    # -- screenshots and movies ------------------------------------------------------------------------------------------
    def _tour_ranges(self) -> Dict[str, Tuple[float, float]]:
        return {v.name: v.tour.time_range for v in self.viz.views if v.tour is not None and v.tour.time_range}
