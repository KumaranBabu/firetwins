"""Entity base class, observer protocol and shared sentinels."""
from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, PrivateAttr


logger = logging.getLogger(__name__)


_MISSING = object()  # sentinel for filter() — distinguishes "absent" from None


class Observer:
    """Lightweight observer interface used by FdsEntity / FdsProject."""
    def update(self, event_type: str, payload: Any = None) -> None:
        pass


class FdsEntity(BaseModel):
    """
    Abstract base for all FDS namelist objects.

    ``_uid`` is a private UUID used internally for dict indexing.
    It is NEVER written to the FDS output file.
    The ``name`` attribute maps to the FDS ``ID=`` parameter.
    """
    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

    # Internal unique key — never serialized to FDS
    _uid: str = PrivateAttr(default_factory=lambda: str(uuid.uuid4()))
    _observers: List[Observer] = PrivateAttr(default_factory=list)

    # GUI / workflow metadata — never written to the FDS file
    enabled: bool = True
    tags: List[str] = Field(default_factory=list)
    #: Parameters of this namelist that PyFDS has no typed field for, as
    #: ``{FDS_KEY: fds_value_text}`` in source order. Re-emitted verbatim by the
    #: writer so an import/export round trip never silently drops them.
    fds_extra: Optional[Dict[str, str]] = None

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def id(self) -> str:
        """Backward-compat alias for ``name`` (FDS ID= parameter)."""
        return getattr(self, "name", "")

    def bbox(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        """
        Return axis-aligned bounding box as ``(x_min, x_max, y_min, y_max, z_min, z_max)``.

        Returns ``None`` for non-geometric entities (Surface, Ramp, Material, …).
        For point entities (Device) returns a degenerate box at the point.
        """
        # XB-style entities (Mesh, Obstruction, Vent, …)
        if all(hasattr(self, a) for a in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")):
            try:
                return (
                    float(self.x_min), float(self.x_max),  # type: ignore[attr-defined]
                    float(self.y_min), float(self.y_max),  # type: ignore[attr-defined]
                    float(self.z_min), float(self.z_max),  # type: ignore[attr-defined]
                )
            except (TypeError, ValueError):
                pass
        # Point entities (Device)
        if hasattr(self, "xyz") and self.xyz is not None:  # type: ignore[attr-defined]
            try:
                x, y, z = (float(v) for v in self.xyz)  # type: ignore[attr-defined]
                return (x, x, y, y, z, z)
            except (TypeError, ValueError):
                pass
        return None

    def add_observer(self, observer: Observer) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def notify(self, event_type: str, data: Any = None) -> None:
        for obs in self._observers:
            obs.update(event_type, data)

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        # Notify observers of property mutations (BUG-06 fix)
        if not name.startswith("_"):
            self.notify("OBJECT_MODIFIED", {"attr": name, "value": value, "entity": self})
