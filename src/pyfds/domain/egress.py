"""
PyFDS Egress Coupling
=====================
Data model for fire+egress co-simulation scenarios.

This module provides lightweight data containers that can be populated from
an FDS project and passed to external egress/evacuation solvers (e.g.
Pathfinder, STEPS, FDS+Evac, or custom agent-based tools).

The model is intentionally solver-agnostic — fields map to the lowest
common denominator across evacuation software rather than any single tool's
input format.

Typical usage
-------------
::

    from pyfds import FdsApi
    from pyfds.domain.egress import EgressScenario, ExitZone, OccupantGroup

    scenario = EgressScenario(
        fds_chid="hotel_fire",
        t_start_evac=60.0,           # s – FDS time when evacuation begins
        exits=[
            ExitZone(id="EXIT_NORTH", xb=(9.9, 10.0, 2.0, 4.0, 0.0, 3.0)),
            ExitZone(id="EXIT_SOUTH", xb=(9.9, 10.0, 6.0, 8.0, 0.0, 3.0)),
        ],
        occupant_groups=[
            OccupantGroup(id="FLOOR1", count=50, start_region=(0,10,0,10,0,3)),
        ],
        hazard_channels=["TC_01", "CO_DEVC"],
        tenability_limits={"TEMPERATURE": 60.0, "CO_PPM": 1400.0},
    )

    # Serialise for export
    data = scenario.to_dict()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Sub-components
# ---------------------------------------------------------------------------

@dataclass
class ExitZone:
    """Describes a physical exit/door available for evacuation."""
    id: str
    xb: Tuple[float, float, float, float, float, float]
    capacity: Optional[int] = None       # max persons per second (None = unlimited)
    door_width: float = 0.9              # metres
    door_height: float = 2.1             # metres
    accessible: bool = True              # ADA / wheelchair accessible
    notes: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "xb": list(self.xb),
            "door_width_m": self.door_width,
            "door_height_m": self.door_height,
            "accessible": self.accessible,
        }
        if self.capacity is not None:
            d["capacity_per_s"] = self.capacity
        if self.notes:
            d["notes"] = self.notes
        return d


@dataclass
class OccupantGroup:
    """
    A group of occupants with shared mobility and behavioural properties.

    ``start_region`` is an XB 6-tuple defining the spatial region where
    the group is initially placed.
    """
    id: str
    count: int
    start_region: Tuple[float, float, float, float, float, float]
    speed_mean: float = 1.2        # m/s (SFPE default for ambulatory adults)
    speed_std:  float = 0.2        # m/s
    pre_movement_mean: float = 60.0  # s
    pre_movement_std:  float = 30.0  # s
    mobility: str = "ambulatory"   # ambulatory | wheelchair | assisted
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "count": self.count,
            "start_region": list(self.start_region),
            "speed": {"mean_m_s": self.speed_mean, "std_m_s": self.speed_std},
            "pre_movement_s": {
                "mean": self.pre_movement_mean,
                "std": self.pre_movement_std,
            },
            "mobility": self.mobility,
            **({"notes": self.notes} if self.notes else {}),
        }


@dataclass
class TenabilityLimit:
    """A single tenability criterion applied to an FDS device quantity."""
    quantity: str          # FDS quantity string, e.g. "TEMPERATURE"
    threshold: float       # value above which space is untenable
    units: str = ""        # informational, e.g. "°C" or "ppm"

    def to_dict(self) -> dict:
        return {"quantity": self.quantity, "threshold": self.threshold,
                **({"units": self.units} if self.units else {})}


# ---------------------------------------------------------------------------
# Top-level scenario
# ---------------------------------------------------------------------------

@dataclass
class EgressScenario:
    """
    Fire-egress co-simulation scenario specification.

    Links an FDS simulation (identified by *fds_chid*) with the occupant
    distribution, exit layout, and tenability criteria required by an
    evacuation solver.

    Parameters
    ----------
    fds_chid:
        FDS CHID (case identifier) of the corresponding fire simulation.
    t_start_evac:
        FDS simulation time at which evacuation is triggered (seconds).
    exits:
        List of available exit zones.
    occupant_groups:
        List of occupant groups (populations with shared properties).
    hazard_channels:
        FDS device names whose time-series data feeds the tenability model.
    tenability_limits:
        Mapping of FDS quantity → threshold value defining untenable conditions.
        Shorthand for a list of :class:`TenabilityLimit` items.
    description:
        Free-text description of the scenario.
    """
    fds_chid: str
    t_start_evac: float = 0.0
    exits: List[ExitZone] = field(default_factory=list)
    occupant_groups: List[OccupantGroup] = field(default_factory=list)
    hazard_channels: List[str] = field(default_factory=list)
    tenability_limits: Dict[str, float] = field(default_factory=dict)
    description: str = ""

    # ── Computed helpers ───────────────────────────────────────────────────

    @property
    def total_occupants(self) -> int:
        return sum(g.count for g in self.occupant_groups)

    @property
    def exit_ids(self) -> List[str]:
        return [e.id for e in self.exits]

    # ── Serialisation ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "fds_chid": self.fds_chid,
            "t_start_evac_s": self.t_start_evac,
            "total_occupants": self.total_occupants,
            "exits": [e.to_dict() for e in self.exits],
            "occupant_groups": [g.to_dict() for g in self.occupant_groups],
            "hazard_channels": self.hazard_channels,
            "tenability_limits": [
                {"quantity": q, "threshold": v}
                for q, v in self.tenability_limits.items()
            ],
            **({"description": self.description} if self.description else {}),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EgressScenario":
        """Reconstruct from a dict produced by :meth:`to_dict`."""
        exits = [
            ExitZone(
                id=e["id"],
                xb=tuple(e["xb"]),  # type: ignore[arg-type]
                capacity=e.get("capacity_per_s"),
                door_width=e.get("door_width_m", 0.9),
                door_height=e.get("door_height_m", 2.1),
                accessible=e.get("accessible", True),
                notes=e.get("notes", ""),
            )
            for e in data.get("exits", [])
        ]
        groups = [
            OccupantGroup(
                id=g["id"],
                count=g["count"],
                start_region=tuple(g["start_region"]),  # type: ignore[arg-type]
                speed_mean=g.get("speed", {}).get("mean_m_s", 1.2),
                speed_std=g.get("speed", {}).get("std_m_s", 0.2),
                pre_movement_mean=g.get("pre_movement_s", {}).get("mean", 60.0),
                pre_movement_std=g.get("pre_movement_s", {}).get("std", 30.0),
                mobility=g.get("mobility", "ambulatory"),
                notes=g.get("notes", ""),
            )
            for g in data.get("occupant_groups", [])
        ]
        limits = {
            item["quantity"]: item["threshold"]
            for item in data.get("tenability_limits", [])
        }
        return cls(
            fds_chid=data["fds_chid"],
            t_start_evac=data.get("t_start_evac_s", 0.0),
            exits=exits,
            occupant_groups=groups,
            hazard_channels=data.get("hazard_channels", []),
            tenability_limits=limits,
            description=data.get("description", ""),
        )
