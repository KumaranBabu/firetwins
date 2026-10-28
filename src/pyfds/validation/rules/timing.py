"""&TIME and &DUMP sanity: the simulated window and the output intervals that fit in it."""
from __future__ import annotations

from typing import Any, List

from ._common import _e, _i, _w
from ..engine import ValidationResult

# (DumpParams field, FDS keyword, what it writes); DT_PL3D is left out: its 10 s default is not a user choice
_INTERVALS = (("dt_slcf", "DT_SLCF", "slices"), ("dt_bndf", "DT_BNDF", "boundary files"),
              ("dt_isof", "DT_ISOF", "isosurfaces"), ("dt_devc", "DT_DEVC", "device output"),
              ("dt_ctrl", "DT_CTRL", "control output"), ("dt_hrr", "DT_HRR", "the heat release file"))


class TimeAndOutputRule:
    """T_END comes after T_BEGIN, and each output interval fits inside the simulated time."""
    name = "TimeAndOutput"

    def check(self, p: Any) -> List[ValidationResult]:
        t0, t1 = p.params.t_begin, p.params.t_end
        if t1 < t0:
            return [_e(self.name, f"&TIME T_END={t1:g} s is before T_BEGIN={t0:g} s.",
                       hint="Set T_END later than T_BEGIN.")]
        if t1 == t0:
            return [_i(self.name, "&TIME T_END equals T_BEGIN: FDS only sets the case up and simulates no time.",
                       hint="Fine for checking the geometry; set T_END for a real run.")]
        if getattr(p.dump, "nframes", None):              # NFRAMES spreads the output over the run instead
            return []
        span = t1 - t0
        long = [f"{key}={getattr(p.dump, attr):g} s ({what})" for attr, key, what in _INTERVALS
                if getattr(p.dump, attr, None) is not None and getattr(p.dump, attr) > span]
        if not long:
            return []
        return [_w(self.name, f"&DUMP output interval longer than the {span:g} s run: {', '.join(long)}.",
                   hint="That output gets only its first frame; shorten the interval or lengthen the run.")]
