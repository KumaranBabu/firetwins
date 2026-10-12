"""ViewerExtras: skybox, units, time display and rendering preferences."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Optional, Sequence

from pyfds.results.viz import model as vm


class ViewerExtrasPrefsMixin:
    # -- skybox, display, units, preferences -------------------------------------------------------------------------------
    def set_skybox(self, kind: str, files: Sequence[str] = (), z_rotation: float = 0.0, show: bool = True,
                   compress_textures: bool = False) -> vm.Skybox:
        need = {"none": 0, "predefined": 0, "image360": 1, "cubemap": 1, "split_cubemap": 6}
        if kind not in need:
            raise ValueError(f"skybox must be one of {', '.join(need)}")
        if len(files) != need[kind]:
            raise ValueError(f"a {kind} skybox needs {need[kind]} image file(s), got {len(files)}")
        missing = [f for f in files if not Path(f).exists()]
        if missing:
            raise FileNotFoundError(f"skybox image not found: {missing[0]}")
        self.viz.skybox = vm.Skybox(kind, [str(Path(f).resolve()) for f in files], float(z_rotation), bool(show), bool(compress_textures))
        self.dirty = True
        return self.viz.skybox

    def set_units(self, temperature: Optional[str] = None, concentration: Optional[str] = None,
                  mass_fraction: Optional[str] = None) -> vm.Units:
        trial = copy.deepcopy(self.viz.units)
        for k, v in (("temperature", temperature), ("concentration", concentration), ("mass_fraction", mass_fraction)):
            if v is not None:
                setattr(trial, k, v)
        bad = trial.problems()
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.units = trial
        self.dirty = True
        return trial

    def set_time_display(self, mode: str) -> None:
        if mode not in ("none", "time", "date_time"):
            raise ValueError("time display must be none, time or date_time")
        self.viz.time_display = mode
        self.dirty = True

    def set_timelines(self, **fields: Any) -> vm.Timelines:
        from pyfds.results.viz import timelines as tml
        trial = copy.deepcopy(self.viz.timelines)
        for k, v in fields.items():
            if k not in vm.Timelines.__dataclass_fields__:
                raise AttributeError(f"unknown timeline setting {k!r}")
            setattr(trial, k, v)
        bad = tml.check(trial)
        if bad:
            raise ValueError("; ".join(bad))
        if trial.view_timeline == "custom" and trial.end <= trial.begin:
            raise ValueError("a custom timeline needs End Time after Begin Time")
        self.viz.timelines = trial
        self._playback = None
        self.dirty = True
        return trial

    def set_motion_blur(self, on: bool) -> None:
        self.viz.motion_blur = bool(on)
        self.dirty = True

    def set_general(self, **fields: Any) -> vm.GeneralPreferences:
        for k in fields:
            if k not in vm.GeneralPreferences.__dataclass_fields__:
                raise AttributeError(f"unknown preference {k!r}")
        for k, v in fields.items():
            setattr(self.viz.general, k, v)
        self.dirty = True
        return self.viz.general

    def set_rendering(self, preset: Optional[str] = None, **fields: Any) -> vm.RenderingPreferences:
        trial = copy.deepcopy(self.viz.rendering)
        if preset == "max_quality":
            trial.max_quality()
        elif preset == "max_compatibility":
            trial.max_compatibility()
        elif preset is not None:
            raise ValueError("preset must be max_quality or max_compatibility")
        for k, v in fields.items():
            if k not in vm.RenderingPreferences.__dataclass_fields__:
                raise AttributeError(f"unknown rendering option {k!r}")
            setattr(trial, k, v)
        bad = trial.problems()
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.rendering = trial
        self.dirty = True
        return trial
