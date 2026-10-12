"""ViewerExtras: CSV series and time history."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

from pyfds.results.viz import csvload as cl
from pyfds.results.viz import model as vm


class ViewerExtrasDataMixin:
    # -- CSV time series ----------------------------------------------------------------------------------------------
    def load_csv(self, path: str, **fields: Any) -> cl.CsvData:
        """File ▸ Load CSV File: a known FDS file is recognised by its name; otherwise give the header layout."""
        ref = cl.guess_type(path)
        for k, v in fields.items():
            if k not in vm.CsvFileRef.__dataclass_fields__ or k == "path":
                raise AttributeError(f"unknown CSV setting {k!r}")
            setattr(ref, k, v)
        data = cl.load(ref)                                     # raises with a plain message when unusable
        ref.path = str(Path(path).resolve())
        self.viz.csv_files = [c for c in self.viz.csv_files if c.path != ref.path] + [ref]
        self.csv_cache[ref.path] = data
        self._rebuild()
        self.dirty = True
        return data

    def remove_csv(self, path: str) -> None:
        p = str(Path(path).resolve())
        n = len(self.viz.csv_files)
        self.viz.csv_files = [c for c in self.viz.csv_files if c.path != p]
        if len(self.viz.csv_files) == n:
            raise KeyError(f"{path} is not loaded")
        self.csv_cache.pop(p, None)
        self._rebuild()
        self.dirty = True

    def csv_series(self) -> Dict[str, cl.TimeSeries]:
        """``{id: series}`` of every loaded CSV column and every Data3D point."""
        out: Dict[str, cl.TimeSeries] = {}
        for ref in self.viz.csv_files:
            data = self.csv_cache.get(ref.path)
            if data is None:
                try:
                    data = self.csv_cache[ref.path] = cl.load(ref)
                except (OSError, ValueError):
                    continue
            for s in data.series:
                out[f"{Path(ref.path).name}/{s.label}"] = s
        for p in self.viz.data3d_points:
            t, v = self.point_series(p.id)
            out[f"Data3D/{p.id}"] = cl.TimeSeries(p.id, p.quantity, "", t, v)
        return out

    def time_history(self, ids: Sequence[str]) -> List[cl.TimeSeries]:
        allv = self.csv_series()
        missing = [i for i in ids if i not in allv]
        if missing:
            raise KeyError(f"no time series {missing[0]!r}; have {sorted(allv)[:6]}")
        return [allv[i] for i in ids]

    def export_data(self, ids: Sequence[str], path: str, tab_separated: bool = False) -> int:
        return cl.export(self.time_history(ids), path, "\t" if tab_separated else ",")
