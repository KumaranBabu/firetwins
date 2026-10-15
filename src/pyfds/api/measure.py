"""Measurements: ``api.measure`` (UX-14). Stateless; a front end keeps the measurements it shows."""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from pyfds.domain import measure as _m


def _xb(entity: Any) -> List[float]:
    try:
        return [entity.x_min, entity.x_max, entity.y_min, entity.y_max, entity.z_min, entity.z_max]
    except AttributeError:
        raise ValueError(f"{getattr(entity, 'name', entity)!r} has no position to measure") from None


class MeasureManager:
    def __init__(self, api) -> None:
        self._api = api

    def distance(self, p: Sequence[float], q: Sequence[float]) -> Dict[str, float]:
        return _m.distance(p, q)

    def angle(self, a: Sequence[float], vertex: Sequence[float], c: Sequence[float]) -> float:
        return _m.angle(a, vertex, c)

    def path_length(self, points: Sequence[Sequence[float]]) -> float:
        return _m.path_length(points)

    def area(self, points: Sequence[Sequence[float]]) -> float:
        return _m.polygon_area(points)

    def between(self, a: Any, b: Any) -> Dict[str, float]:
        """Gap and centre distance between two objects that have x/y/z bounds."""
        return _m.box_gap(_xb(self._resolve(a)), _xb(self._resolve(b)))

    def size(self, entity: Any) -> Dict[str, float]:
        return _m.box_size(_xb(self._resolve(entity)))

    def _resolve(self, e: Any) -> Any:
        if isinstance(e, str):
            for attr in sorted(set(self._api.project._TYPE_MAP.values())):
                for item in getattr(self._api.project, attr):
                    if getattr(item, "name", None) == e and hasattr(item, "x_min"):
                        return item
            raise KeyError(f"{e!r} not found")
        return e
