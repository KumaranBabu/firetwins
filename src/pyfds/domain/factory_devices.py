"""EntityFactory: devices, props and slices."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class EntityFactoryDevicesMixin:
    def create_thermocouple(
        self,
        name: str,
        xyz: Tuple[float, float, float],
        *,
        quantity: str = "TEMPERATURE",
        prop_id: Optional[str] = None,
    ) -> Any:
        from pyfds.domain.model import Device
        return Device(
            name=name, quantity=quantity,
            x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]),
            prop_id=prop_id,
        )

    def create_heat_flux_gauge(
        self,
        name: str,
        xyz: Tuple[float, float, float],
        orientation: Tuple[float, float, float] = (0.0, 0.0, -1.0),
    ) -> Any:
        from pyfds.domain.model import Device
        return Device(
            name=name, quantity="HEAT FLUX",
            x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]),
            orientation=orientation,
        )

    def create_smoke_detector(
        self,
        name: str,
        xyz: Tuple[float, float, float],
        prop_id: str,
    ) -> Any:
        from pyfds.domain.model import Device
        return Device(
            name=name, quantity="CHAMBER OBSCURATION",
            x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]),
            prop_id=prop_id,
        )

    def create_sprinkler(
        self,
        name: str,
        xyz: Tuple[float, float, float],
        prop_id: str,
    ) -> Any:
        from pyfds.domain.model import Device
        return Device(
            name=name, quantity="TIME",
            x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]),
            prop_id=prop_id,
        )

    def create_sprinkler_prop(
        self,
        name: str,
        *,
        rti: float = 50.0,
        c_factor: float = 0.7,
        spray_angle: Tuple[float, float] = (60.0, 80.0),
        flow_rate: Optional[float] = None,
        particle_velocity: Optional[float] = None,
        operating_pressure: Optional[float] = None,
    ) -> Any:
        from pyfds.domain.model import Prop
        kw: Dict[str, Any] = dict(
            name=name, quantity="SPRINKLER LINK TEMPERATURE",
            rti=rti, c_factor=c_factor, spray_angle=spray_angle,
        )
        if flow_rate is not None:
            kw["flow_rate"] = flow_rate
        if particle_velocity is not None:
            kw["particle_velocity"] = particle_velocity
        if operating_pressure is not None:
            kw["operating_pressure"] = operating_pressure
        return Prop(**kw)

    def create_smoke_detector_prop(
        self,
        name: str,
        *,
        obscuration: float = 3.28,
        length: float = 1.8,
        characteristic_velocity: float = 0.36,
    ) -> Any:
        from pyfds.domain.model import Prop
        return Prop(
            name=name, quantity="SMOKE DETECTOR",
            activation_obscuration=obscuration,
            length=length,
            characteristic_velocity=characteristic_velocity,
        )

    def create_slice(
        self,
        name: str,
        quantity: str,
        plane: str,
        position: float,
        *,
        vector: bool = False,
        quantity2: Optional[str] = None,
    ) -> Any:
        from pyfds.domain.model import Slice
        kw: Dict[str, Any] = dict(name=name, quantity=quantity,
                                   plane=plane.upper(), position=position,
                                   vector=vector)
        if quantity2:
            kw["quantity2"] = quantity2
        return Slice(**kw)
