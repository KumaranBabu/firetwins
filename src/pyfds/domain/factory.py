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
from typing import Any, Dict, Tuple, Type

from .factory_devices import (  # noqa: F401  (re-exported)
    EntityFactoryDevicesMixin,
)
from .factory_geometry import (  # noqa: F401  (re-exported)
    EntityFactoryGeometryMixin,
)
from .factory_hvac import (  # noqa: F401  (re-exported)
    EntityFactoryHvacMixin,
)
from .factory_physics import (  # noqa: F401  (re-exported)
    EntityFactoryPhysicsMixin,
)


logger = logging.getLogger(__name__)


class EntityFactory(EntityFactoryGeometryMixin, EntityFactoryDevicesMixin, EntityFactoryPhysicsMixin, EntityFactoryHvacMixin):
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

    def register(self, method_name: str, factory_fn: Any) -> None:
        """Register a named custom factory function."""
        self._custom[method_name] = factory_fn

    def __getattr__(self, name: str) -> Any:
        if name in self.__dict__.get("_custom", {}):
            return self._custom[name]
        raise AttributeError(f"EntityFactory has no method {name!r}")

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
