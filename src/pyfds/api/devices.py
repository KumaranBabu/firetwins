"""Devices and controls.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List

from .base import _CollectionManager

logger = logging.getLogger(__name__)


class DeviceManager(_CollectionManager):
    def __init__(self, api):
        from pyfds.domain.model import Device
        super().__init__(api, Device)

    def add_thermocouple(self, xyz: List[float], devc_id: str = "", **kwargs) -> Any:
        from pyfds.domain.model import Device
        # NB: Device.id is a read-only alias for .name (see FdsEntity) — the
        # constructor kwarg must be name=, not id=, or it's silently dropped
        # into pydantic's extra="allow" bucket and every device ends up
        # named "DefaultDevice".
        d = Device(xyz=xyz, quantity="TEMPERATURE", name=devc_id or f"TC_{len(self.all())+1:03d}",
                   **kwargs)
        self.add(d)
        return d

    def add_sprinkler(self, xyz: List[float], prop_id: str, **kwargs) -> Any:
        from pyfds.domain.model import Device
        d = Device(xyz=xyz, quantity="TIME", prop_id=prop_id,
                   name=kwargs.pop("id", None) or f"SPK_{len(self.all())+1:03d}",
                   **kwargs)
        self.add(d)
        return d

    def add_device(self, quantity: str, xyz: List[float], **kwargs) -> Any:
        """Generic sensor: any valid FDS DEVC quantity (smoke/heat detector,
        nozzle, flow gauge, gas/solid-phase probe, ...), not just the
        thermocouple/sprinkler convenience constructors above."""
        from pyfds.domain.model import Device
        from pyfds.domain.quantities import validate_quantity, CONTEXT_DEVC
        if not validate_quantity(quantity, CONTEXT_DEVC):
            raise ValueError(f"{quantity!r} is not a valid FDS DEVC quantity")
        name = kwargs.pop("name", None) or kwargs.pop("id", None) or f"DEVC_{len(self.all())+1:03d}"
        d = Device(xyz=xyz, quantity=quantity, name=name, **kwargs)
        self.add(d)
        return d


class ControlManager(_CollectionManager):
    def __init__(self, api):
        from pyfds.domain.model import Control
        super().__init__(api, Control)

    def add_control(self, function_type: str, input_ids=None, name: str = "", **fields) -> Any:
        """Add a ``&CTRL``. *function_type* must be a known FDS function and the inputs/parameters
        it needs must be present (see ``pyfds.domain.control_functions``)."""
        from pyfds.domain.model import Control
        from pyfds.domain.control_functions import problems
        ids = [input_ids] if isinstance(input_ids, str) else list(input_ids or [])
        ctrl = Control(name=name or f"CTRL_{len(self.all()) + 1:03d}",
                       function_type=function_type.strip().upper(),
                       input_ids=ids or None, **fields)
        bad = problems(ctrl)
        if bad:
            raise ValueError("; ".join(bad))
        if self.get(ctrl.name) is not None:
            raise ValueError(f"control {ctrl.name!r} already exists")
        self.add(ctrl)
        return ctrl
