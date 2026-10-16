"""Devices and controls.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .base import _CollectionManager
from .device_systems import DeviceSystems

logger = logging.getLogger(__name__)


class DeviceManager(DeviceSystems, _CollectionManager):
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

    # -- activation controls: what a control drives and what drives it (Edit Activation Controls) -------------
    def _ctrl(self, name_or_entity):
        c = self.get(name_or_entity) if isinstance(name_or_entity, str) else name_or_entity
        if c is None or c not in self.all():
            raise KeyError(f"control {name_or_entity!r} not found")
        return c

    def problems(self, control_or_name) -> List[str]:
        """What is wrong with a control's function, inputs and parameters (empty list = fine). Accepts a control
        that is not in the project too (an edited copy), so a dialog can check before it saves."""
        from pyfds.domain.control_functions import problems
        c = self.get(control_or_name) if isinstance(control_or_name, str) else control_or_name
        if c is None:
            raise KeyError(f"control {control_or_name!r} not found")
        return problems(c)

    @staticmethod
    def functions() -> List[Dict[str, Any]]:
        """Every FUNCTION_TYPE: [{name, description, kind, inputs, required}] (kind groups them in the editor)."""
        from pyfds.domain.control_functions import CONTROL_FUNCTIONS
        return [{"name": f.name, "description": f.description, "kind": f.kind, "inputs": f.inputs,
                 "required": list(f.required)} for f in CONTROL_FUNCTIONS.values()]

    def controlled(self, name_or_entity) -> List[Tuple[str, Any]]:
        """Objects switched by this control (their CTRL_ID names it): [(type name, entity)]."""
        c = self._ctrl(name_or_entity)
        return [(type(e).__name__, e) for e in self._project.all_entities
                if e is not c and getattr(e, "ctrl_id", None) == c.name]

    def used_as_input(self, name_or_entity) -> List[Any]:
        """Other controls that take this one as an input."""
        c = self._ctrl(name_or_entity)
        return [o for o in self.all() if o is not c and c.name in self.inputs_of(o)]

    @staticmethod
    def inputs_of(control) -> List[str]:
        return list(control.input_ids or ([control.input_id] if control.input_id else []))

    def depends_on(self, control, target_name: str, _seen: Optional[set] = None) -> bool:
        """Does *control* (through its inputs) depend on the control called *target_name*?"""
        seen = _seen if _seen is not None else set()
        for n in self.inputs_of(control):
            if n == target_name:
                return True
            other = self.get(n)
            if other is not None and n not in seen:
                seen.add(n)
                if self.depends_on(other, target_name, seen):
                    return True
        return False

    def input_candidates(self, name_or_entity) -> List[str]:
        """Names that may be inputs of this control: every device and every control that does not (indirectly)
        depend on it, so a loop cannot be made."""
        c = self._ctrl(name_or_entity)
        out = [d.name for d in self._api.devices.all()]
        out += [o.name for o in self.all() if o is not c and not self.depends_on(o, c.name)]
        return out

    def set_inputs(self, name_or_entity, names) -> Any:
        """Set the inputs of a control (one undo step); refuses unknown names and loops."""
        c = self._ctrl(name_or_entity)
        names = list(dict.fromkeys(names))
        allowed = set(self.input_candidates(c))
        bad = [n for n in names if n not in allowed]
        if bad:
            raise ValueError(f"cannot use as input: {', '.join(bad)} (unknown, or it would make a loop)")
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        res = self._pipe.execute(GroupCommand([ModifyPropertyCommand(c, "input_ids", names or None),
                                               ModifyPropertyCommand(c, "input_id", None)],
                                              label=f"set inputs of {c.name}"))
        if not res.success:
            raise ValueError(res.message)
        return c

    def assign(self, name_or_entity, entity: Any) -> Any:
        """Make *entity* (an obstruction, vent, hole, device, HVAC part, ramp ...) activated by this control."""
        c = self._ctrl(name_or_entity)
        if "ctrl_id" not in type(entity).model_fields:
            raise ValueError(f"{type(entity).__name__} cannot be switched by a control")
        self._api.set_property(entity, "ctrl_id", c.name)
        return entity

    def unassign(self, entity: Any) -> Any:
        """Stop an object being switched by a control."""
        if not getattr(entity, "ctrl_id", None):
            raise ValueError(f"{getattr(entity, 'name', entity)!r} is not controlled")
        empty_is_none = type(entity).model_fields["ctrl_id"].default is None
        self._api.set_property(entity, "ctrl_id", None if empty_is_none else "")
        return entity

    def assignable(self) -> List[Tuple[str, Any]]:
        """Every object that can carry a CTRL_ID: [(type name, entity)]."""
        return [(type(e).__name__, e) for e in self._project.all_entities
                if "ctrl_id" in type(e).model_fields and getattr(e, "name", None)]

    def rename(self, entity_or_name, new_name: str) -> Any:
        """Rename a control and every reference to it (CTRL_ID of objects, inputs of other controls)."""
        c = self._ctrl(entity_or_name)
        if not new_name.strip():
            raise ValueError("a name cannot be empty")
        old = c.name
        if new_name == old:
            return c
        if self.get(new_name) is not None or any(d.name == new_name for d in self._api.devices.all()):
            raise ValueError(f"{new_name!r} is already used by a control or device")
        users, followers = self.controlled(c), self.used_as_input(c)
        with self._api.history.transaction(f"rename control {old} to {new_name}"):
            self.update(c, name=new_name)
            for _kind, e in users:
                self._api.set_property(e, "ctrl_id", new_name)
            for o in followers:
                self._api.set_property(o, "input_ids", [new_name if n == old else n for n in self.inputs_of(o)])
                if o.input_id:
                    self._api.set_property(o, "input_id", None)
        return c
