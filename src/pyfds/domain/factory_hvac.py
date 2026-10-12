"""EntityFactory: HVAC filters, leakages, nodes and ducts."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class EntityFactoryHvacMixin:
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
