"""ViewerManager: colour bars."""
from __future__ import annotations

import copy
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from pyfds.results.viz import colorbar as cb
from pyfds.results.viz import model as vm
from pyfds.results.viz import units as un
from pyfds.results.viz.tree import RESULT_KINDS


class ViewerManagerColorbarsMixin:
    # -- colorbars -------------------------------------------------------------------------------------------
    def colorbars(self) -> List[Tuple[str, str, cb.ColorbarModel]]:
        """One colorbar per quantity among the active results that use one (smoke and plain particles do not)."""
        out, seen = [], set()
        leaves = [l for l in self.tree.leaves() if l.kind in RESULT_KINDS]
        for leaf in self.active_leaves():
            if leaf.kind not in RESULT_KINDS or leaf.kind in ("max_error",) or leaf.quantity in seen:
                continue
            if leaf.kind == "particles":
                props = self.viz.particles.get(str(leaf.data.get("class")))
                if not props or props.color == "default":
                    continue
            if leaf.kind == "smoke3d" and leaf.quantity.upper() in ("SOOT DENSITY",):
                continue
            if leaf.kind == "isosurface" or leaf.kind.startswith("data3d_"):
                continue
            seen.add(leaf.quantity)
            _, units = un.convert(np.zeros(1), leaf.units, self.viz.units)
            out.append((leaf.quantity, units, self.dataset.colorbar(leaf.quantity, leaf.units, leaves)))
        return out

    def colorbar(self, quantity: str) -> cb.ColorbarModel:
        leaves = [l for l in self.tree.leaves() if l.kind in RESULT_KINDS and l.quantity == quantity]
        if not leaves or self.dataset is None:
            raise KeyError(f"no results of quantity {quantity!r}")
        return self.dataset.colorbar(quantity, leaves[0].units, [l for l in self.tree.leaves() if l.kind in RESULT_KINDS])

    def set_colorbar(self, quantity: str, **fields: Any) -> vm.ColorbarProps:
        """Change colorbar properties; nothing changes when any value is invalid."""
        props = self.viz.fds.colorbar(quantity)
        unknown = set(fields) - set(vm.ColorbarProps.__dataclass_fields__)
        if unknown:
            raise AttributeError(f"unknown colorbar properties: {sorted(unknown)}")
        trial = copy.deepcopy(props)
        for k, v in fields.items():
            setattr(trial, k, v)
        bad = trial.problems()
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.fds.colorbars[quantity] = trial
        self.dirty = True
        return trial

    def copy_colorbar(self, source: str, targets: Sequence[str]) -> None:
        """The Copy button of FDS Preferences: give other quantities the same colorbar settings."""
        src = self.viz.fds.colorbar(source)
        for q in targets:
            self.viz.fds.colorbars[q] = copy.deepcopy(src)
        self.dirty = True

    def reset_colorbar(self, quantity: str) -> None:
        self.viz.fds.colorbars[quantity] = vm.default_colorbar(quantity)
        self.dirty = True

    def highlight_colorbar(self, quantity: str, fraction: Optional[float], width_fraction: float = 0.05) -> None:
        """Click on the colorbar adds a highlight region there; ``None`` (right-click) removes it."""
        props = self.viz.fds.colorbar(quantity)
        if fraction is None:
            cb.clear_highlight(props)
        else:
            bar = self.colorbar(quantity)
            cb.highlight_at(props, bar.lo, bar.hi, fraction, width_fraction)
        self.dirty = True
