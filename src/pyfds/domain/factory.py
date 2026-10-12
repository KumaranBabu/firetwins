"""
PyFDS Entity Factory
=====================
Factory Pattern implementation for standardized FDS entity creation.

Responsibilities
----------------
* Enforce required-field validation at construction time (before the entity
  reaches the project/command pipeline).
* Provide high-level named constructors (``create_burner``,
  ``create_thermocouple``, etc.) that hide Pydantic field names from callers.
* Allow plugins to register custom factory methods.
* Keep domain logic out of the GUI and API controller layers.

Usage::

    factory = EntityFactory()

    mesh = factory.create(Mesh, name="Room", ijk=(20,20,15),
                          xb=(0,4,0,4,0,3))

    burner = factory.create_burner(name="Fire", xb=(1,2,1,2,0,0),
                                   hrrpua=500.0)

    tc = factory.create_thermocouple(name="TC_01", xyz=(2.0,2.0,2.5))

    spk = factory.create_sprinkler(name="SPK_01", xyz=(2,2,2.4),
                                   prop_id="RTI-50")
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)


class EntityFactory:
    """
    Creates FDS domain entities with validated defaults.

    All ``create_*`` methods return ready-to-use entity instances.
    They do NOT add entities to the project — that is the CommandPipeline's job.

    The generic ``create(cls, **kwargs)`` method accepts the same keyword
    arguments as the entity's ``__init__`` and maps positional shorthands
    (``xb``, ``ijk``, ``xyz``) to the named coordinate fields.

    Plugin integration
    ------------------
    Register a custom factory method::

        factory.register("create_atrium_fire",
                         lambda **kw: factory.create_burner(name=kw["name"],
                                                             xb=kw["xb"],
                                                             hrrpua=2000.0))
    """

    def __init__(self) -> None:
        self._custom: Dict[str, Any] = {}

    # ── Generic factory ───────────────────────────────────────────────────────

    def create(self, cls: Type, **kwargs: Any) -> Any:
        """
        Create an entity of type *cls*, translating shorthand kwargs.

        Shorthand mappings
        ------------------
        ``xb=(x0,x1,y0,y1,z0,z1)`` → expands to x_min/x_max/y_min/y_max/z_min/z_max
        ``ijk=(i,j,k)``             → expands to cell_count=(i,j,k) on Mesh
        ``xyz=(x,y,z)``             → expands to x=, y=, z= on Device/Prop/HvacNode
        ``name``                    → passed through unchanged
        """
        kwargs = self._expand_shorthands(kwargs)
        try:
            return cls(**kwargs)
        except Exception as exc:
            logger.error("EntityFactory.create(%s): %s", cls.__name__, exc)
            raise

    # ── Named constructors ────────────────────────────────────────────────────

    def create_mesh(
        self,
        name: str,
        ijk: Tuple[int, int, int],
        xb: Tuple[float, ...],
        *,
        mpi_rank: Optional[int] = None,
        color: Optional[str] = None,
        cylindrical: bool = False,
    ) -> Any:
        from pyfds.domain.model import Mesh
        kw: Dict[str, Any] = dict(name=name, cell_count=tuple(int(v) for v in ijk))
        kw.update(self._xb_dict(xb))
        if mpi_rank is not None:
            kw["mpi_processor"] = mpi_rank
        if color:
            kw["color"] = color
        if cylindrical:
            kw["cylindrical"] = True
        return Mesh(**kw)

    def create_obstruction(
        self,
        name: str,
        xb: Tuple[float, ...],
        surf_id: str = "INERT",
        *,
        color: str = "GRAY",
        ctrl_id: Optional[str] = None,
        mult_id: Optional[str] = None,
        transparency: float = 0.0,
    ) -> Any:
        from pyfds.domain.model import Obstruction
        kw = dict(name=name, surface_id=surf_id, color=color,
                  transparency=transparency)
        kw.update(self._xb_dict(xb))
        if ctrl_id:
            kw["ctrl_id"] = ctrl_id
        if mult_id:
            kw["mult_id"] = mult_id
        return Obstruction(**kw)

    def create_burner(
        self,
        name: str,
        xb: Tuple[float, ...],
        hrrpua: float,
        *,
        tau_q: float = 1.0,
        ramp_q: Optional[str] = None,
        color: str = "RED",
    ) -> Any:
        """Create a burning surface (SURF with HRRPUA set)."""
        from pyfds.domain.model import Surface
        kw: Dict[str, Any] = dict(
            name=name,
            heat_release_rate=hrrpua,
            tau_q=tau_q,
            color=color,
        )
        if ramp_q:
            kw["ramp_q"] = ramp_q
        return Surface(**kw)

    def create_vent(
        self,
        name: str,
        xb: Tuple[float, ...],
        surf_id: str = "OPEN",
        *,
        ctrl_id: Optional[str] = None,
        dynamic_pressure: Optional[float] = None,
    ) -> Any:
        from pyfds.domain.model import Vent
        kw = dict(name=name, surface_id=surf_id)
        kw.update(self._xb_dict(xb))
        if ctrl_id:
            kw["ctrl_id"] = ctrl_id
        if dynamic_pressure is not None:
            kw["dynamic_pressure"] = dynamic_pressure
        return Vent(**kw)

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

    def create_reaction(
        self,
        name: str,
        fuel: str,
        heat_of_combustion: float,
        *,
        soot_yield: float = 0.0,
        co_yield: float = 0.0,
        radiative_fraction: float = 0.35,
    ) -> Any:
        from pyfds.domain.model import Reaction
        return Reaction(
            name=name, fuel=fuel,
            heat_of_combustion=heat_of_combustion,
            soot_yield=soot_yield,
            co_yield=co_yield,
            radiative_fraction=radiative_fraction,
        )

    def create_ramp(
        self,
        name: str,
        times: List[float],
        values: List[float],
    ) -> Any:
        from pyfds.domain.model import Ramp
        return Ramp(name=name, times=times, values=values)

    def create_t_squared_ramp(
        self,
        name: str,
        t_end: float,
        alpha: float = 0.0117,
        n_points: int = 20,
    ) -> Any:
        """Create a t² fire growth ramp (HRR = alpha * t²)."""
        import math
        from pyfds.domain.model import Ramp
        dt = t_end / (n_points - 1)
        times  = [i * dt for i in range(n_points)]
        peak   = alpha * t_end * t_end
        values = [alpha * t * t / peak for t in times]
        return Ramp(name=name, times=times, values=values)

    def create_hrr_curve(
        self,
        name: str,
        hrrpua: float,
        fire_area: float,
        *,
        growth: str = "medium",
        t_growth: Optional[float] = None,
        t_steady: float = 300.0,
        t_decay: float = 120.0,
        n_points: int = 30,
    ) -> Any:
        """
        Build a normalised HRR-vs-time Ramp covering growth → steady → decay.

        The ramp is normalised to peak = 1.0; multiply by HRRPUA on the SURF.

        Parameters
        ----------
        name:
            Ramp ID (referenced by SURF RAMP_Q).
        hrrpua:
            Peak HRRPUA (kW/m²) — informational; used to derive alpha when
            *t_growth* is None.
        fire_area:
            Estimated fire area (m²) — used to scale alpha.
        growth:
            Named t² growth category: 'slow' | 'medium' | 'fast' | 'ultrafast'.
            Ignored when *t_growth* is given explicitly.
        t_growth:
            Override growth phase duration (s).  When provided, *growth* is
            ignored and the curve reaches peak at this time.
        t_steady:
            Duration of the steady-burning phase (s).
        t_decay:
            Duration of the decay phase (s).
        n_points:
            Number of Ramp data points.
        """
        from pyfds.domain.model import Ramp

        _ALPHA = {"slow": 0.00293, "medium": 0.01172, "fast": 0.04689, "ultrafast": 0.18758}
        alpha = _ALPHA.get(growth.lower(), _ALPHA["medium"])
        q_peak = hrrpua * fire_area  # kW

        if t_growth is not None:
            tg = float(t_growth)
        elif q_peak > 0:
            import math
            tg = math.sqrt(q_peak / alpha)
        else:
            tg = 300.0

        t_total = tg + t_steady + t_decay
        dt = t_total / (n_points - 1)
        times: List[float] = []
        values: List[float] = []

        for i in range(n_points):
            t = i * dt
            if t <= tg:
                v = (t / tg) ** 2 if tg > 0 else 0.0
            elif t <= tg + t_steady:
                v = 1.0
            else:
                frac = (t - tg - t_steady) / t_decay if t_decay > 0 else 1.0
                v = max(0.0, 1.0 - frac)
            times.append(round(t, 3))
            values.append(round(v, 6))

        return Ramp(name=name, times=times, values=values)

    def create_hole(
        self,
        name: str,
        xb: Tuple[float, ...],
        *,
        ctrl_id: Optional[str] = None,
    ) -> Any:
        from pyfds.domain.model import Hole
        kw = dict(name=name)
        kw.update(self._xb_dict(xb))
        if ctrl_id:
            kw["ctrl_id"] = ctrl_id
        return Hole(**kw)

    def create_wind_profile(
        self,
        name: str,
        *,
        heights: Optional[List[float]] = None,
        speeds: Optional[List[float]] = None,
        direction: float = 0.0,
        speed: Optional[float] = None,
        z0: Optional[float] = None,
    ) -> Any:
        """Create a WIND namelist entity describing an atmospheric wind profile."""
        from pyfds.domain.model import WindProfile
        kw: Dict[str, Any] = dict(name=name, direction=direction)
        if heights is not None:
            kw["heights"] = heights
        if speeds is not None:
            kw["speeds"] = speeds
        if speed is not None:
            kw["speed"] = speed
        if z0 is not None:
            kw["z0"] = z0
        return WindProfile(**kw)

    def create_move(
        self,
        name: str,
        *,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        rotation_angle: Optional[float] = None,
        axis: Optional[Tuple[float, float, float]] = None,
        scale: float = 1.0,
    ) -> Any:
        """Create a MOVE namelist entity for geometry transformation."""
        from pyfds.domain.model import Move
        kw: Dict[str, Any] = dict(name=name, x=x, y=y, z=z, scale=scale)
        if rotation_angle is not None:
            kw["rotation_angle"] = rotation_angle
        if axis is not None:
            kw["axis"] = list(axis)
        return Move(**kw)

    def create_hvac_filter(
        self,
        name: str,
        *,
        node_id: str = "",
        loss_forward: float = 0.0,
        loss_reverse: float = 0.0,
        filter_type: Optional[str] = None,
    ) -> Any:
        """Create an HVAC FILTER namelist entity."""
        from pyfds.domain.model import HvacFilter
        kw: Dict[str, Any] = dict(
            name=name, node_id=node_id,
            loss_forward=loss_forward, loss_reverse=loss_reverse,
        )
        if filter_type is not None:
            kw["filter_type"] = filter_type
        return HvacFilter(**kw)

    def create_hvac_leakage(
        self,
        name: str,
        zone_id_1: str,
        zone_id_2: str,
        *,
        crack_length: float = 0.0,
        crack_width: float = 0.001,
        multiplier: float = 1.0,
    ) -> Any:
        """Create an HVAC LEAK namelist entity for inter-zone leakage."""
        from pyfds.domain.model import HvacLeakage
        return HvacLeakage(
            name=name,
            zone_id_1=zone_id_1,
            zone_id_2=zone_id_2,
            crack_length=crack_length,
            crack_width=crack_width,
            multiplier=multiplier,
        )

    def create_hvac_ambient_node(self, name: str, xyz: Tuple[float, float, float]) -> Any:
        from pyfds.domain.model import HvacNode
        return HvacNode(name=name, x=xyz[0], y=xyz[1], z=xyz[2], ambient=True)

    def create_hvac_duct(
        self,
        name: str,
        node_id_1: str,
        node_id_2: str,
        diameter: float,
        *,
        length: Optional[float] = None,
    ) -> Any:
        from pyfds.domain.model import HvacDuct
        kw: Dict[str, Any] = dict(name=name, node_id_1=node_id_1,
                                   node_id_2=node_id_2, diameter=diameter)
        if length is not None:
            kw["length"] = length
        return HvacDuct(**kw)

    # ── Custom factory registration (Plugin hook) ─────────────────────────────

    def register(self, method_name: str, factory_fn: Any) -> None:
        """Register a named custom factory function."""
        self._custom[method_name] = factory_fn

    def __getattr__(self, name: str) -> Any:
        if name in self.__dict__.get("_custom", {}):
            return self._custom[name]
        raise AttributeError(f"EntityFactory has no method {name!r}")

    # ── Shorthand expansion helpers ───────────────────────────────────────────

    @staticmethod
    def _xb_dict(xb: Tuple[float, ...]) -> Dict[str, float]:
        if len(xb) != 6:
            raise ValueError(f"XB must have 6 values, got {len(xb)}")
        keys = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
        return dict(zip(keys, xb))

    @staticmethod
    def _expand_shorthands(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(kwargs)
        if "xb" in out:
            xb = out.pop("xb")
            out.update(EntityFactory._xb_dict(tuple(xb)))
        if "ijk" in out:
            ijk = out.pop("ijk")
            out["cell_count"] = tuple(int(v) for v in ijk)
        if "xyz" in out:
            xyz = out.pop("xyz")
            out["x"] = float(xyz[0])
            out["y"] = float(xyz[1])
            out["z"] = float(xyz[2])
        return out

    def __repr__(self) -> str:
        return f"<EntityFactory custom_methods={list(self._custom.keys())}>"
