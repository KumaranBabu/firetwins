"""Fire library and liquid pool fires (B4: FIR-03, FIR-06). Accessible via ``api.fires``."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from pyfds.domain import fire_library as fl

from .base import _UndoableStore
from .species import _unique

if TYPE_CHECKING:
    from .facade import FdsApi


class FireManager(_UndoableStore):
    """HRR-curve library and fire builders.

    Built-in items are formula fires (t-squared classes, steady); ``save_item`` keeps your own curves in the
    project (with their source note). ``add_from_library`` turns an item into a burner: a ramp, a burner
    surface (HRRPUA from the item's peak and the fire's area) and a pan obstruction.
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    # per-project saved curves: {name: {"times", "hrr", "description", "source"}}
    @property
    def _items(self) -> Dict[str, Dict[str, Any]]:
        return self._api.project.editor.fire_items

    def _capture_state(self):
        return {k: dict(v) for k, v in self._items.items()}

    def _restore_state(self, state) -> None:
        self._items.clear()
        self._items.update(state)

    # -- library ---------------------------------------------------------------------
    def names(self, peak_kw: float = 1000.0) -> List[str]:
        return list(fl.builtin_items(peak_kw)) + [n for n in self._items]

    def get(self, name: str, peak_kw: float = 1000.0) -> fl.FireItem:
        """A library item. Built-in formula fires are scaled to *peak_kw*; saved curves ignore it."""
        if name in self._items:
            d = self._items[name]
            return fl.FireItem(name, d.get("description", ""), tuple(d["times"]), tuple(d["hrr"]), d.get("source", ""))
        built = fl.builtin_items(peak_kw)
        if name not in built:
            raise KeyError(f"fire {name!r} not found; choose from {', '.join(self.names())}")
        return built[name]

    def growth_curve(self, alpha: float, peak_kw: float, steady_s: float = 0.0, decay_s: float = 0.0):
        """``(times, hrr)`` of a t-squared fire (alpha in kW/s^2: slow 0.00293, medium 0.01172, fast 0.04689,
        ultra-fast 0.1876)."""
        return fl.t2_growth(alpha, peak_kw, steady_s, decay_s)

    def save_item(self, name: str, times: Sequence[float], hrr_kw: Sequence[float], description: str = "",
                  source: str = "") -> fl.FireItem:
        """Keep an HRR curve in the project (one undo step). Say where the data came from in *source*."""
        bad = fl.validate_curve(list(times), list(hrr_kw))
        if bad:
            raise ValueError(bad)
        if name in fl.builtin_items():
            raise ValueError(f"{name!r} is a built-in fire; choose another name")
        entry = {"times": [float(t) for t in times], "hrr": [float(q) for q in hrr_kw],
                 "description": description, "source": source}
        self._do(f"save fire {name}", lambda: self._items.__setitem__(name, entry))
        return self.get(name)

    def remove_item(self, name: str) -> None:
        if name not in self._items:
            raise KeyError(f"saved fire {name!r} not found")
        self._do(f"remove fire {name}", lambda: self._items.pop(name))

    # -- builders --------------------------------------------------------------------
    def add_from_library(self, item: str, xb: Sequence[float], peak_kw: float = 1000.0, name: Optional[str] = None,
                         pan_height: float = 0.1, scale: float = 1.0) -> Dict[str, Any]:
        """Burner from a library fire (one undo step). *xb* = ``[x1, x2, y1, y2, z]`` or a 6-value box whose
        top face burns; the pan is *pan_height* m tall. HRR is the item's curve times *scale*. Returns
        ``{"ramp", "surface", "obstruction", "item"}``."""
        it = self.get(item, peak_kw)
        if scale <= 0:
            raise ValueError("scale must be positive")
        if len(xb) == 5:
            x1, x2, y1, y2, z = xb
            box = [x1, x2, y1, y2, z, z + pan_height]
        elif len(xb) == 6:
            box = list(xb)
        else:
            raise ValueError("xb is [x1, x2, y1, y2, z] or [x1, x2, y1, y2, z1, z2]")
        area = (box[1] - box[0]) * (box[3] - box[2])
        if area <= 0 or box[5] <= box[4]:
            raise ValueError("the burner must have an area and a height")
        peak = it.peak * scale
        base = name or _unique(self._api.surfaces, item.upper().replace(" ", "_"))
        with self._api.history.transaction(f"add fire {item}"):
            ramp = self._api.ramps.add_ramp(f"{base}_RAMP", list(it.times), [q / it.peak for q in it.hrr])
            surf = self._api.surfaces.add_burner(peak / area, tau_q=None, name=base, ramp_q=ramp.name, color="RED")
            obst = self._api.obstructions.add_obstruction(box, surface_ids=[surf.name, "INERT", "INERT"],
                                                          name=_unique(self._api.obstructions, f"{base}_PAN"))
        return {"ramp": ramp, "surface": surf, "obstruction": obst, "item": it}

    def add_pool_fire(self, fuel: str, xb: Sequence[float], depth: float = 0.01, name: Optional[str] = None,
                      pan_height: float = 0.05) -> Dict[str, Any]:
        """Liquid pool fire (one undo step): a pan whose top is a surface made of the liquid-fuel material
        *fuel* (``api.materials.add_liquid_fuel``) *depth* metres deep. *xb* is ``[x1, x2, y1, y2, z]``. The
        burning rate then follows from the fuel's properties and the heat feedback; returns the pieces and the
        pool's area and equivalent diameter."""
        mat = self._api.materials.get(fuel)
        if mat is None:
            raise KeyError(f"material {fuel!r} not found")
        if not self._api.materials.is_liquid_fuel(mat):
            raise ValueError(f"material {fuel!r} is not a liquid fuel (needs a boiling temperature); "
                             "use api.materials.add_liquid_fuel")
        if depth <= 0 or pan_height <= 0:
            raise ValueError("depth and pan_height must be positive")
        if len(xb) != 5:
            raise ValueError("xb is [x1, x2, y1, y2, z]")
        x1, x2, y1, y2, z = xb
        area = (x2 - x1) * (y2 - y1)
        if area <= 0:
            raise ValueError("the pool has no area")
        from pyfds.domain.model import Surface, Layer
        base = name or _unique(self._api.surfaces, f"POOL_{fuel}".replace(" ", "_"))
        with self._api.history.transaction(f"add pool fire {base}"):
            surf = Surface(name=base, color="ORANGE", backing="INSULATED",
                           layers=[Layer(material_id=fuel, thickness=depth)])
            self._api.surfaces.add(surf)
            obst = self._api.obstructions.add_obstruction(
                [x1, x2, y1, y2, z, z + pan_height], surface_ids=[base, "INERT", "INERT"],
                name=_unique(self._api.obstructions, f"{base}_PAN"))
        return {"surface": surf, "obstruction": obst, "area": area,
                "equivalent_diameter": math.sqrt(4.0 * area / math.pi)}
