"""HVAC network components.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from .base import _CollectionManager
from .hvac_extras import FanCurves, JetFans

logger = logging.getLogger(__name__)


class HvacNodeManager(_CollectionManager):
    """Manage HVAC network connection points (&NODE)."""
    def __init__(self, api):
        from pyfds.domain.model import HvacNode
        super().__init__(api, HvacNode)

    def add_node(self, xyz: List[float], *, vent_id: Optional[str] = None,
                 ambient: bool = False, **kwargs) -> Any:
        from pyfds.domain.model import HvacNode
        node = HvacNode(x=xyz[0], y=xyz[1], z=xyz[2], vent_id=vent_id, ambient=ambient, **kwargs)
        self.add(node)
        return node


class HvacDuctManager(_CollectionManager):
    """Manage HVAC duct segments connecting two nodes (&DUCT)."""
    def __init__(self, api):
        from pyfds.domain.model import HvacDuct
        super().__init__(api, HvacDuct)

    def add_duct(self, node_id_1: str, node_id_2: str, diameter: float = 0.5, **kwargs) -> Any:
        from pyfds.domain.model import HvacDuct
        duct = HvacDuct(node_id_1=node_id_1, node_id_2=node_id_2, diameter=diameter, **kwargs)
        self.add(duct)
        return duct


class FanManager(FanCurves, _CollectionManager):
    """Manage HVAC fans (&FAN)."""
    def __init__(self, api):
        from pyfds.domain.model import Fan
        super().__init__(api, Fan)

    def add_fan(self, duct_id: str, volume_flow_rate: Optional[float] = None, **kwargs) -> Any:
        from pyfds.domain.model import Fan
        fan = Fan(duct_id=duct_id, volume_flow_rate=volume_flow_rate, **kwargs)
        self.add(fan)
        return fan


class DamperManager(_CollectionManager):
    """Manage HVAC dampers (&DAMPER)."""
    def __init__(self, api):
        from pyfds.domain.model import Damper
        super().__init__(api, Damper)

    def add_damper(self, duct_id: str, ctrl_id: str, **kwargs) -> Any:
        from pyfds.domain.model import Damper
        damper = Damper(duct_id=duct_id, ctrl_id=ctrl_id, **kwargs)
        self.add(damper)
        return damper


class HvacFilterManager(_CollectionManager):
    """Manage HVAC particulate filters (&FILTER)."""
    def __init__(self, api):
        from pyfds.domain.model import HvacFilter
        super().__init__(api, HvacFilter)

    def add_filter(self, duct_id: str, efficiency: float = 0.9, **kwargs) -> Any:
        from pyfds.domain.model import HvacFilter
        f = HvacFilter(duct_id=duct_id, efficiency=efficiency, **kwargs)
        self.add(f)
        return f


class HvacLeakageManager(_CollectionManager):
    """Manage HVAC duct-leakage paths between pressure zones (&LEAK)."""
    def __init__(self, api):
        from pyfds.domain.model import HvacLeakage
        super().__init__(api, HvacLeakage)

    def add_leakage(self, zone_id_1: str, zone_id_2: str, area: float = 0.001, **kwargs) -> Any:
        from pyfds.domain.model import HvacLeakage
        leak = HvacLeakage(zone_id_1=zone_id_1, zone_id_2=zone_id_2, area=area, **kwargs)
        self.add(leak)
        return leak


class HvacAircoilManager(_CollectionManager):
    """Manage duct heat exchangers (&AIRCOIL)."""
    def __init__(self, api):
        from pyfds.domain.model import HvacAircoil
        super().__init__(api, HvacAircoil)

    def add_aircoil(self, duct_id: str, effectiveness: float = 0.8, **kwargs) -> Any:
        from pyfds.domain.model import HvacAircoil
        if duct_id not in {d.name for d in self._project.hvac_ducts}:
            raise KeyError(f"duct {duct_id!r} not found")
        if not 0 < effectiveness <= 1:
            raise ValueError("effectiveness must be in (0, 1]")
        coil = HvacAircoil(duct_id=duct_id, effectiveness=effectiveness, **kwargs)
        self.add(coil)
        return coil


class HvacManager(JetFans):
    """Whole-network operations on the HVAC system: ``api.hvac``.

    (Per-component collections live on ``api.hvac_nodes``, ``api.hvac_ducts``,
    ``api.fans`` …)
    """

    def __init__(self, api) -> None:
        self._api = api

    def add_hvac(self, name, vent_ids, area=None, flow_rate=None, **kwargs) -> Any:
        """Add an ``&HVAC`` entity connecting vents (undoable)."""
        from pyfds.domain.model import Hvac
        from pyfds.automation.commands import AddEntityCommand
        h = Hvac(name=name, vent_ids=list(vent_ids), **kwargs)
        if area is not None:
            h.diameter = (4 * area / 3.14159) ** 0.5
        if flow_rate is not None:
            h.length = float(flow_rate)
        self._api.history.execute(AddEntityCommand(self._api.project, h))
        return h

    def solve_network(self, rho=1.2, max_iter=200, tol=1e-5):
        """Solve the steady duct-network pressure/flow balance."""
        from pyfds.domain.hvac_solver import HvacNetworkSolver
        solver = HvacNetworkSolver(self._api.project, rho=rho, max_iter=max_iter, tol=tol)
        return solver.solve()
