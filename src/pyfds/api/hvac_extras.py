"""Fan curves and jet fans on the HVAC API (B4: HVC-04, HVC-07). Mixins for ``FanManager`` / ``HvacManager``.

FDS (User Guide 10.2.4): a user fan curve is a RAMP of *pressure drop (Pa) against volume flow (m3/s)*
(``T`` = flow, ``F`` = pressure); a quadratic fan has MAX_FLOW and MAX_PRESSURE; a constant fan has
VOLUME_FLOW. A free-standing jet fan is a thin obstruction with an HVAC vent on each face, joined by a duct
with a fan (10.1, example ``jet_fan``).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .species import _unique

RHO_AIR = 1.2


def quadratic_curve(max_flow: float, max_pressure: float, n: int = 12) -> List[Tuple[float, float]]:
    """Sample FDS's quadratic fan model as ``(flow, pressure)`` points: ``dp = Pmax (1 - sign(V) (V/Vmax)^2)``,
    from reverse flow (-Vmax) through shut-off to 1.7 Vmax, ready for :meth:`FanManager.set_curve`."""
    if max_flow <= 0 or max_pressure <= 0:
        raise ValueError("max_flow and max_pressure must be positive")
    if n < 3:
        raise ValueError("use at least 3 points")
    lo, hi = -max_flow, 1.7 * max_flow
    out = []
    for i in range(n):
        v = lo + (hi - lo) * i / (n - 1)
        sign = 1.0 if v >= 0 else -1.0
        out.append((round(v, 6), round(max_pressure * (1.0 - sign * (v / max_flow) ** 2), 6)))
    return out


def jet_fan_thrust(flow: float, area: float, rho: float = RHO_AIR) -> float:
    """Momentum thrust of a jet of *flow* m3/s through *area* m2: ``rho Q^2 / A`` (N)."""
    if flow < 0 or area <= 0 or rho <= 0:
        raise ValueError("flow must be zero or more; area and rho positive")
    return rho * flow * flow / area


def jet_fan_flow(thrust: float, area: float, rho: float = RHO_AIR) -> float:
    """The volume flow (m3/s) that gives *thrust* newtons through *area* m2."""
    if thrust < 0 or area <= 0 or rho <= 0:
        raise ValueError("thrust must be zero or more; area and rho positive")
    return (thrust * area / rho) ** 0.5


class FanCurves:
    """Mixin for ``FanManager``."""

    def set_curve(self, fan, flows: Sequence[float], pressures: Sequence[float], ramp_id: Optional[str] = None) -> Any:
        """Give a fan a user curve (one undo step): *pressures* (Pa) against *flows* (m3/s). Flow must increase
        from point to point and pressure must not rise with flow. Replaces any constant or quadratic setting."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        f = self.get(fan) if isinstance(fan, str) else fan
        if f is None:
            raise KeyError(f"fan {fan!r} not found")
        flows, pressures = [float(v) for v in flows], [float(v) for v in pressures]
        if len(flows) != len(pressures) or len(flows) < 2:
            raise ValueError("give at least two points, with one pressure per flow")
        if any(b <= a for a, b in zip(flows, flows[1:])):
            raise ValueError("flows must be strictly increasing")
        if any(b > a for a, b in zip(pressures, pressures[1:])):
            raise ValueError("pressure must not increase with flow (a fan delivers less pressure at higher flow)")
        rid = ramp_id or f.ramp_id or _unique(self._api.ramps, f"{f.name}_CURVE")
        with self._api.history.transaction(f"set fan curve {f.name}"):
            old = self._api.ramps.get(rid)
            if old is not None:
                self._api.ramps.remove(old)
            self._api.ramps.add_ramp(rid, flows, pressures)
            self._api.history.execute(GroupCommand([
                ModifyPropertyCommand(f, "ramp_id", rid), ModifyPropertyCommand(f, "volume_flow_rate", None),
                ModifyPropertyCommand(f, "max_flow", None), ModifyPropertyCommand(f, "max_pressure", None)],
                label=f"fan {f.name} uses curve {rid}"))
        return f

    def curve(self, fan) -> Dict[str, Any]:
        """How the fan is defined: ``{"kind": constant|quadratic|curve|none, ...}`` with the curve points."""
        f = self.get(fan) if isinstance(fan, str) else fan
        if f is None:
            raise KeyError(f"fan {fan!r} not found")
        if f.ramp_id:
            r = self._api.ramps.get(f.ramp_id)
            pts = list(zip(r.times, r.values)) if r is not None else []
            return {"kind": "curve", "ramp_id": f.ramp_id, "points": pts}
        if f.max_flow is not None or f.max_pressure is not None:
            return {"kind": "quadratic", "max_flow": f.max_flow, "max_pressure": f.max_pressure}
        if f.volume_flow_rate is not None:
            return {"kind": "constant", "volume_flow": f.volume_flow_rate}
        return {"kind": "none"}


class JetFans:
    """Mixin for ``HvacManager``."""

    jet_fan_thrust = staticmethod(jet_fan_thrust)
    jet_fan_flow = staticmethod(jet_fan_flow)

    def add_jet_fan(self, center: Sequence[float], direction: str = "+x", width: float = 1.0, height: float = 1.0,
                    flow: Optional[float] = None, thrust: Optional[float] = None, thickness: Optional[float] = None,
                    name: str = "JETFAN", surf_id: str = "INERT") -> Dict[str, Any]:
        """A free-standing jet fan blowing along *direction* (``+x -x +y -y +z -z``) with a *width* x *height*
        face at *center*. Give the volume *flow* (m3/s) or the *thrust* (N, converted with rho 1.2 kg/m3).

        Builds (one undo step) a thin obstruction at least one cell thick, an HVAC vent on each face, a node
        at each vent, a duct from the suction side to the discharge side and the fan. Returns the pieces and
        the thrust. The face should line up with the mesh cells."""
        d = direction.strip().lower()
        if len(d) != 2 or d[0] not in "+-" or d[1] not in "xyz":
            raise ValueError("direction is one of +x -x +y -y +z -z")
        if (flow is None) == (thrust is None):
            raise ValueError("give exactly one of flow or thrust")
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        area = width * height
        q = float(flow) if flow is not None else jet_fan_flow(thrust, area)
        if q <= 0:
            raise ValueError("flow must be positive")
        api = self._api
        res = api.geom._resolution(None)
        t = max(thickness if thickness is not None else res, res)
        axis = "xyz".index(d[1])
        cross = [i for i in range(3) if i != axis]
        extent = {cross[0]: width, cross[1]: height} if axis != 1 else {0: width, 2: height}
        if axis == 2:
            extent = {0: width, 1: height}
        lo, hi = [0.0] * 3, [0.0] * 3
        for i in range(3):
            half = (t if i == axis else extent[i]) / 2.0
            lo[i], hi[i] = center[i] - half, center[i] + half
        mesh = next((m for m in api.meshes.all() if m.x_min <= center[0] <= m.x_max and m.y_min <= center[1] <= m.y_max
                     and m.z_min <= center[2] <= m.z_max), None)
        if mesh is not None:                    # put the plate on cell faces (at least one cell thick)
            for i in range(3):
                o = (mesh.x_min, mesh.y_min, mesh.z_min)[i]
                c = ((mesh.x_max - mesh.x_min) / mesh.cell_count[0], (mesh.y_max - mesh.y_min) / mesh.cell_count[1],
                     (mesh.z_max - mesh.z_min) / mesh.cell_count[2])[i]
                a = o + round((lo[i] - o) / c) * c
                b = o + round((hi[i] - o) / c) * c
                if b - a < c * 0.999:
                    b = a + c
                lo[i], hi[i] = round(a, 9), round(b, 9)

        def xb(face_coord):
            box = []
            for i in range(3):
                box += [face_coord, face_coord] if i == axis else [lo[i], hi[i]]
            return box

        suction, discharge = (lo[axis], hi[axis]) if d[0] == "+" else (hi[axis], lo[axis])
        base = name if api.obstructions.get(name) is None else _unique(api.obstructions, name)
        with api.history.transaction(f"add jet fan {base}"):
            plate = api.obstructions.add_obstruction(
                [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]], surf_id=surf_id, name=base)
            v_in = api.vents.add_vent(xb(suction), surf_id="HVAC", name=f"{base}_IN")
            v_out = api.vents.add_vent(xb(discharge), surf_id="HVAC", name=f"{base}_OUT")
            n_in = api.hvac_nodes.add_node([0, 0, 0], vent_id=v_in.name, name=f"{base}_NODE_IN")
            n_out = api.hvac_nodes.add_node([0, 0, 0], vent_id=v_out.name, name=f"{base}_NODE_OUT")
            duct = api.hvac_ducts.add_duct(n_in.name, n_out.name, area=area, name=f"{base}_DUCT")
            fan = api.fans.add_fan(duct.name, volume_flow_rate=q, name=f"{base}_FAN")
        return {"obstruction": plate, "vents": [v_in, v_out], "nodes": [n_in, n_out], "duct": duct, "fan": fan,
                "flow": q, "thrust": jet_fan_thrust(q, area)}
