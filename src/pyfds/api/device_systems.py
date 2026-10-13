"""Detector and sprinkler systems built from several devices (B4: DEV-08, 09, 10, 14, 15, 16, HVC-06, OUT-08).

A mixin for ``DeviceManager``. Each builder creates all the pieces inside one history transaction (one
undo step) and checks what it refers to first. Syntax follows the FDS User Guide (6.10), sections
18.3 (detectors), 18.5 (control functions), 22.10 (FED) and 22.16 (HVAC output).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .species import _unique

HVAC_PREFIXES = ("DUCT ", "NODE ", "FAN ", "AIRCOIL ", "FILTER ")


class DeviceSystems:
    """Mixin for ``DeviceManager`` (needs ``_api``, ``_project``, ``add``, ``get``, ``all``)."""

    # -- helpers ---------------------------------------------------------------------
    def _name(self, name: Optional[str], base: str) -> str:
        if name:
            if self.get(name) is not None:
                raise ValueError(f"device {name!r} already exists")
            return name
        return _unique(self, base)

    def _need_prop(self, prop_id: str):
        p = self._api.props.get(prop_id)
        if p is None:
            raise KeyError(f"property set {prop_id!r} not found; create it first (api.props)")
        return p

    # -- nozzle, sprinkler link, dry pipe (DEV-08, DEV-09) -----------------------------
    def add_nozzle(self, xyz: Sequence[float], prop_id: str, ctrl_id: Optional[str] = None,
                   name: Optional[str] = None, orientation: Optional[Sequence[float]] = None, **fields) -> Any:
        """An externally controlled spray nozzle: the property set must name a particle class
        (``part_id``). With *ctrl_id* it sprays while that control is on; without it, from the start."""
        from pyfds.domain.model import Device
        prop = self._need_prop(prop_id)
        if not prop.part_id:
            raise ValueError(f"property set {prop_id!r} has no particle class (part_id), so it cannot spray")
        if ctrl_id is not None and self._api.controls.get(ctrl_id) is None:
            raise KeyError(f"control {ctrl_id!r} not found")
        d = Device(name=self._name(name, "NOZZLE"), xyz=tuple(xyz), prop_id=prop_id, ctrl_id=ctrl_id,
                   quantity="CONTROL" if ctrl_id else "TIME",
                   orientation=tuple(orientation) if orientation else None, **fields)
        self.add(d)
        return d

    def add_sprinkler_link(self, xyz: Sequence[float], prop_id: Optional[str] = None,
                           rti: float = 50.0, activation_temperature: float = 74.0, c_factor: float = 0.7,
                           name: Optional[str] = None) -> Any:
        """A stand-alone thermal link (no spray). Without *prop_id* a property set is made from the
        RTI and activation temperature (one undo step)."""
        from pyfds.domain.model import Device
        with self._api.history.transaction("add sprinkler link"):
            if prop_id is None:
                prop = self._api.props.add_prop(
                    _unique(self._api.props, "LINK"), quantity="LINK TEMPERATURE", rti=rti,
                    c_factor=c_factor, activation_temperature=activation_temperature)
                prop_id = prop.name
            else:
                if self._need_prop(prop_id).quantity not in ("LINK TEMPERATURE", "SPRINKLER LINK TEMPERATURE"):
                    raise ValueError(f"property set {prop_id!r} is not a thermal link (quantity LINK TEMPERATURE)")
            d = Device(name=self._name(name, "LINK"), xyz=tuple(xyz), prop_id=prop_id, quantity="LINK TEMPERATURE")
            self.add(d)
        return d

    def add_dry_pipe_sprinkler(self, xyz: Sequence[float], nozzle_prop: str, delay: float = 30.0,
                               link_prop: Optional[str] = None, rti: float = 50.0,
                               activation_temperature: float = 74.0, name: Optional[str] = None) -> Dict[str, Any]:
        """Sprinkler on a dry pipe: the link activates, then the water arrives *delay* seconds later
        (``TIME_DELAY`` control between link and nozzle). Returns ``{"link", "control", "nozzle"}``."""
        if delay < 0:
            raise ValueError("delay must be zero or positive")
        base = name or _unique(self, "SPK")
        with self._api.history.transaction(f"add dry pipe sprinkler {base}"):
            link = self.add_sprinkler_link(xyz, link_prop, rti=rti, activation_temperature=activation_temperature,
                                           name=f"{base}_link")
            ctrl = self._api.controls.add_control("TIME_DELAY", link.name, name=f"{base}_dry_pipe", delay=delay)
            nozzle = self.add_nozzle(xyz, nozzle_prop, ctrl_id=ctrl.name, name=base)
        return {"link": link, "control": ctrl, "nozzle": nozzle}

    # -- beam detector (DEV-10) ---------------------------------------------------------
    def add_beam_detector(self, xb_line: Sequence[float], setpoint: float = 33.0, name: Optional[str] = None,
                          quantity: str = "PATH OBSCURATION", **fields) -> Any:
        """Beam smoke detector along the line (x1, x2, y1, y2, z1, z2) with a trip point in % obscuration
        (or %/m for ``TRANSMISSION``, which trips when the value falls *below* the setpoint)."""
        from pyfds.domain.model import Device
        if quantity not in ("PATH OBSCURATION", "TRANSMISSION"):
            raise ValueError("quantity must be PATH OBSCURATION or TRANSMISSION")
        if len(xb_line) != 6:
            raise ValueError("the beam needs 6 coordinates: x1, x2, y1, y2, z1, z2")
        a, b = xb_line[0::2], xb_line[1::2]
        if all(abs(p - q) < 1e-9 for p, q in zip(a, b)):
            raise ValueError("the beam has zero length")
        if not 0.0 < setpoint <= 100.0:
            raise ValueError("setpoint is a percentage between 0 and 100")
        d = Device(name=self._name(name, "BEAM"), quantity=quantity, xb=tuple(float(v) for v in xb_line),
                   setpoint=setpoint, trip_direction=1 if quantity == "PATH OBSCURATION" else -1, **fields)
        self.add(d)
        return d

    # -- FED device (DEV-14) -------------------------------------------------------------
    def add_fed_device(self, xyz: Sequence[float], activity: int = 2, quantity: str = "FED",
                       name: Optional[str] = None, **fields) -> Any:
        """Fractional effective dose (``FED``, asphyxiants) or incapacitating concentration (``FIC``,
        irritants) at a point. *activity* 1 rest, 2 light work (default), 3 heavy work: sets the property set
        used by FED (reused when one with that activity exists)."""
        from pyfds.domain.model import Device
        if quantity not in ("FED", "FIC"):
            raise ValueError("quantity must be FED or FIC")
        if activity not in (1, 2, 3):
            raise ValueError("activity is 1 (rest), 2 (light work) or 3 (heavy work)")
        with self._api.history.transaction(f"add {quantity} device"):
            prop_id = None
            if quantity == "FED":
                prop = next((p for p in self._api.props.all()
                             if p.fed_activity == activity and not p.quantity and not p.part_id), None)
                prop = prop or self._api.props.add_prop(_unique(self._api.props, f"FED_ACTIVITY_{activity}"),
                                                        fed_activity=activity)
                prop_id = prop.name
            d = Device(name=self._name(name, quantity), xyz=tuple(xyz), quantity=quantity, prop_id=prop_id, **fields)
            self.add(d)
        return d

    # -- aspiration (VESDA) system (DEV-15) --------------------------------------------------
    def add_aspiration_system(self, detector_xyz: Sequence[float], samplers: Sequence[Dict[str, Any]],
                              setpoint: Optional[float] = None, bypass_flowrate: float = 0.0,
                              name: Optional[str] = None) -> Dict[str, Any]:
        """Aspiration detection: sampling points (each ``{"xyz": [...], "flowrate": kg/s, "delay": s}``)
        draw air to a central detector that reports the flow-weighted obscuration in %/m. *setpoint* is the
        alarm threshold in %/m. Returns ``{"detector", "samplers"}``."""
        from pyfds.domain.model import Device
        if not samplers:
            raise ValueError("an aspiration system needs at least one sampling point")
        for i, s in enumerate(samplers, 1):
            if len(s.get("xyz", ())) != 3:
                raise ValueError(f"sampler {i}: xyz needs 3 coordinates")
            if s.get("flowrate", 0) <= 0:
                raise ValueError(f"sampler {i}: flowrate must be positive (kg/s)")
            if s.get("delay", 0) < 0:
                raise ValueError(f"sampler {i}: delay must be zero or positive (s)")
        if bypass_flowrate < 0:
            raise ValueError("bypass_flowrate must be zero or positive")
        if setpoint is not None and setpoint <= 0:
            raise ValueError("setpoint must be positive")
        base = self._name(name, "ASP")
        with self._api.history.transaction(f"add aspiration system {base}"):
            made = []
            for i, s in enumerate(samplers, 1):
                d = Device(name=f"{base}_sampler_{i}", xyz=tuple(s["xyz"]), quantity="DENSITY", spec_id="SOOT",
                           devc_id=base, flowrate=float(s["flowrate"]), delay=float(s.get("delay", 0.0)))
                self.add(d)
                made.append(d)
            central = Device(name=base, xyz=tuple(detector_xyz), quantity="ASPIRATION",
                             bypass_flowrate=float(bypass_flowrate), setpoint=setpoint)
            self.add(central)
        return {"detector": central, "samplers": made}

    # -- HVAC output (HVC-06, OUT-08) -------------------------------------------------------
    def add_hvac_output(self, quantity: str, duct_id: Optional[str] = None, node_id=None,
                        spec_id: Optional[str] = None, cell_l: Optional[float] = None,
                        name: Optional[str] = None, **fields) -> Any:
        """A device on an HVAC duct or node (duct flow/velocity/temperature, node pressure, fan pressure,
        filter loading ...). Duct, fan and aircoil outputs need *duct_id*; node and filter outputs need
        *node_id* (two nodes for ``NODE PRESSURE DIFFERENCE``); species outputs need *spec_id*; duct-cell
        outputs need *cell_l*."""
        from pyfds.domain.model import Device
        from pyfds.domain.quantities import validate_quantity, CONTEXT_DEVC
        q = quantity.strip().upper()
        if not q.startswith(HVAC_PREFIXES) or not validate_quantity(q, CONTEXT_DEVC):
            raise ValueError(f"{quantity!r} is not an HVAC output quantity")
        nodes = [node_id] if isinstance(node_id, str) else list(node_id or [])
        by_duct = q.startswith(("DUCT ", "FAN ", "AIRCOIL "))
        if by_duct:
            if not duct_id:
                raise ValueError(f"{q} needs duct_id")
            if self._api.hvac_ducts.get(duct_id) is None:
                raise KeyError(f"duct {duct_id!r} not found")
            if nodes:
                raise ValueError(f"{q} takes a duct_id, not node_id")
        else:
            want = 2 if q == "NODE PRESSURE DIFFERENCE" else 1
            if len(nodes) != want:
                raise ValueError(f"{q} needs {want} node_id value(s)")
            for n in nodes:
                if self._api.hvac_nodes.get(n) is None:
                    raise KeyError(f"node {n!r} not found")
            if duct_id:
                raise ValueError(f"{q} takes node_id, not duct_id")
        if ("FRACTION" in q or "LOADING" in q) and not spec_id:
            raise ValueError(f"{q} needs spec_id")
        if "CELL" in q and cell_l is None:
            raise ValueError(f"{q} needs cell_l (metres along the duct from its first node)")
        d = Device(name=self._name(name, "HVAC_OUT"), quantity=q, duct_id=duct_id, node_id=nodes or None,
                   spec_id=spec_id, cell_l=cell_l, **fields)
        self.add(d)
        return d

    # -- time device and run control (DEV-16, CTL-05) ---------------------------------------
    def add_time_device(self, setpoint: float, name: Optional[str] = None, **fields) -> Any:
        """A device that turns on at simulation time *setpoint* (s)."""
        from pyfds.domain.model import Device
        if setpoint < 0:
            raise ValueError("setpoint is a time in seconds, zero or more")
        d = Device(name=self._name(name, "TIME"), quantity="TIME", setpoint=setpoint, **fields)
        self.add(d)
        return d

    def stop_when(self, device: str, restart: bool = False, name: Optional[str] = None) -> Any:
        """End the run when *device* activates (a ``KILL`` control); with *restart* also write a restart
        file at that moment (a second ``RESTART`` control on the same input)."""
        if self.get(device) is None and self._api.controls.get(device) is None:
            raise KeyError(f"device or control {device!r} not found")
        with self._api.history.transaction(f"stop when {device} activates"):
            kill = self._api.controls.add_control("KILL", device, name=name or _unique(self._api.controls, "STOP"))
            if restart:
                self._api.controls.add_control("RESTART", device, name=_unique(self._api.controls, "RESTART"))
        return kill

    def stop_at(self, time: float, name: Optional[str] = None) -> Any:
        """End the run at simulation time *time* (s): a time device plus a ``KILL`` control. (Prefer the
        end time in the simulation parameters unless the stop must be conditional.)"""
        with self._api.history.transaction(f"stop at {time} s"):
            dev = self.add_time_device(time, name=name)
            kill = self.stop_when(dev.name)
        return kill
