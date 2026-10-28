"""&RAMP records: one line per point, gathered per ID; a ramp the editor cannot hold is kept as its text."""
from __future__ import annotations

from typing import Any, Dict

from pyfds.domain.model import FdsProject, Ramp


class RampBuilders:
    def _accumulate_ramp(self, d: Dict, accum: Dict, rec=None) -> None:
        """Collect the (T, F) points of one RAMP ID across its lines (BUG-03 fix).

        A ramp the model cannot hold exactly - a list of times without F (RAMP_TIME, RAMP_UVW), a spatial ramp
        written with X, EXTERNAL_FILE, or any other key - keeps all its lines as text (``why_text`` says why)."""
        ramp_id = self._str(d, "ID", "__unnamed__")
        if ramp_id not in accum:
            accum[ramp_id] = {"times": [], "values": [], "raw": [], "why_text": None,
                              "devc_id": self._str(d, "DEVC_ID") or None, "ctrl_id": self._str(d, "CTRL_ID") or None,
                              "interpolation": self._str(d, "INTERPOLATION") or None}
        acc = accum[ramp_id]
        acc["raw"].append(rec.raw if rec is not None else
                          "&RAMP " + ", ".join(f"{k}={v}" for k, v in d.items() if k != "_TAG") + " /")
        t, f = self._flt(d, "T"), self._flt(d, "F")
        if acc["why_text"] is not None:
            return
        if t is None or f is None:
            acc["why_text"] = "a line has no T or no F"
            return
        if rec is not None:
            extra = self._unused_fields(rec, d.used)
            if extra:
                acc["why_text"] = f"{', '.join(extra)} not held by the ramp editor"
                return
        acc["times"].append(t)
        acc["values"].append(f)

    def _finish_ramps(self, project: FdsProject, accum: Dict[str, Dict[str, Any]]) -> None:
        """Add each gathered ramp as a Ramp, or its lines as text when the editor cannot hold it."""
        for ramp_id, acc in accum.items():
            ramp = None
            times = acc["times"]
            if acc["why_text"] is None and any(b <= a for a, b in zip(times, times[1:])):
                acc["why_text"] = "T values do not increase"
            if acc["why_text"] is None:
                try:
                    ramp = Ramp(name=ramp_id, times=times, values=acc["values"], devc_id=acc["devc_id"],
                                ctrl_id=acc["ctrl_id"], interpolation=acc["interpolation"])
                except Exception as exc:
                    acc["why_text"] = type(exc).__name__
            if ramp is not None:
                project.add_entity(ramp)
            else:
                project.raw_records.extend(acc["raw"])
                self.warnings.append(f"&RAMP ID={ramp_id!r}: {len(acc['raw'])} line(s) kept unchanged as text "
                                     f"({acc['why_text']})")
