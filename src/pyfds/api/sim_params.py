"""Simulation parameters: the global namelists ``&TIME``, ``&DUMP``, ``&MISC``, ``&PRES`` and ``&RADI`` as ``api.sim``.

Every change is validated before anything is touched and is one undo step. Keywords PyFDS has no typed field for live
in the block's ``fds_extra`` (written back verbatim), exactly as on every other object.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_EXTRA_KEY = re.compile(r"^[A-Z][A-Z0-9_]*(\([0-9:, ]+\))?$")

#: key -> (label, project attribute, FDS namelist)
BLOCKS = {
    "time": ("Time", "params", "TIME"),
    "output": ("Output", "dump", "DUMP"),
    "environment": ("Environment", "misc", "MISC"),
    "pressure": ("Pressure", "pres", "PRES"),
    "radiation": ("Radiation", "radi", "RADI"),
}

#: fields that must be positive when set
_POSITIVE = {"dt", "dt_slcf", "dt_pl3d", "dt_bndf", "dt_isof", "dt_devc", "dt_ctrl", "dt_restart", "dt_hrr", "dt_mass",
             "p_inf", "openmp_threads", "number_radiation_angles", "radiation_iterations", "max_pressure_iterations",
             "pressure_iterations", "time_step_increment", "nframes", "column_dump_limit", "maximum_particles",
             "sig_figs", "sig_figs_exp"}


class SimParamsManager:
    def __init__(self, api: Any) -> None:
        self._api = api

    # -- reading ----------------------------------------------------------------------------------------
    def blocks(self) -> List[Dict[str, str]]:
        return [{"key": k, "label": v[0], "namelist": v[2]} for k, v in BLOCKS.items()]

    def _block(self, key: str) -> Any:
        try:
            return getattr(self._api.project, BLOCKS[key][1])
        except KeyError:
            raise KeyError(f"unknown parameter block {key!r}; choose from {', '.join(BLOCKS)}") from None

    def get(self, key: str) -> Any:
        """The live parameter object (``project.params`` / ``dump`` / ``misc`` / ``pres`` / ``radi``)."""
        return self._block(key)

    def values(self, key: str) -> Dict[str, Any]:
        """Typed fields as ``{name: value}`` (without the additional keywords)."""
        return {k: v for k, v in self._block(key).model_dump().items() if k != "fds_extra"}

    def defaults(self, key: str) -> Dict[str, Any]:
        return {k: v for k, v in type(self._block(key))().model_dump().items() if k != "fds_extra"}

    # -- checking ---------------------------------------------------------------------------------------
    def check(self, key: str, **fields: Any) -> List[str]:
        """Problems with the block as it would be after *fields* are applied (empty list = fine)."""
        obj = self._block(key)
        unknown = [f for f in fields if f not in type(obj).model_fields or f == "fds_extra"]
        if unknown:
            return [f"{', '.join(unknown)}: not a parameter of {BLOCKS[key][2]}"]
        merged = {**self.values(key), **fields}
        try:
            new = type(obj)(**merged)
        except Exception as exc:                                  # pydantic type error
            return [str(exc).splitlines()[1].strip() if len(str(exc).splitlines()) > 1 else str(exc)]
        out: List[str] = []
        for name in _POSITIVE:
            v = getattr(new, name, None)
            if v is not None and v <= 0:
                out.append(f"{name.upper()} must be greater than 0")
        if key == "time" and new.t_end <= new.t_begin:
            out.append("T_END must be later than T_BEGIN")
        if key == "environment":
            if not 0.0 <= new.humidity <= 100.0:
                out.append("HUMIDITY must be between 0 and 100 %")
            if not -100.0 <= new.tmpa <= 100.0:
                out.append("TMPA (ambient temperature) must be between -100 and 100 C")
        return out

    # -- changing ---------------------------------------------------------------------------------------
    def update(self, key: str, **fields: Any) -> Any:
        """Change several fields of one block as ONE undo step. Nothing is applied if anything is invalid."""
        if not fields:
            return self._block(key)
        problems = self.check(key, **fields)
        if problems:
            raise ValueError("; ".join(problems))
        obj = self._block(key)
        coerced = type(obj)(**{**self.values(key), **fields})      # the values as the model will hold them
        changes = {k: getattr(coerced, k) for k in fields if getattr(obj, k) != getattr(coerced, k)}
        if changes:
            from pyfds.automation.commands import ModifyPropertyCommand
            with self._api.history.transaction(f"edit {BLOCKS[key][2]} parameters"):
                for name, value in changes.items():
                    self._api.history.execute(ModifyPropertyCommand(obj, name, value))
        return obj

    def reset(self, key: str) -> Any:
        """Put every typed field of the block back to its default (one undo step)."""
        return self.update(key, **self.defaults(key))

    def extras(self, key: str) -> Dict[str, str]:
        return dict(self._block(key).fds_extra or {})

    def set_extra(self, key: str, name: str, value: Any) -> None:
        from pyfds.automation.commands import ModifyPropertyCommand
        obj = self._block(key)
        name = name.strip().upper()
        if not _EXTRA_KEY.match(name):
            raise ValueError(f"{name!r} is not a valid FDS keyword")
        base = name.split("(")[0].lower()
        if base in type(obj).model_fields and base != "fds_extra":
            raise ValueError(f"{name} is a typed field of {BLOCKS[key][2]}; use update({base}=...)")
        text = (".TRUE." if value else ".FALSE.") if isinstance(value, bool) else str(value).strip()
        if not text:
            raise ValueError("value must not be empty")
        self._api.history.execute(ModifyPropertyCommand(obj, "fds_extra", {**(obj.fds_extra or {}), name: text}))

    def remove_extra(self, key: str, name: str) -> None:
        from pyfds.automation.commands import ModifyPropertyCommand
        obj = self._block(key)
        name = name.strip().upper()
        merged = dict(obj.fds_extra or {})
        if name not in merged:
            raise KeyError(f"{name} is not set in {BLOCKS[key][2]}")
        del merged[name]
        self._api.history.execute(ModifyPropertyCommand(obj, "fds_extra", merged or None))

    def set_extras(self, key: str, table: Dict[str, str]) -> None:
        """Make the additional keywords of the block equal *table* (one undo step)."""
        old = self.extras(key)
        with self._api.history.transaction(f"edit {BLOCKS[key][2]} keywords"):
            for name in set(old) - {n.strip().upper() for n in table}:
                self.remove_extra(key, name)
            for name, value in table.items():
                if old.get(name.strip().upper()) != str(value).strip():
                    self.set_extra(key, name, value)
