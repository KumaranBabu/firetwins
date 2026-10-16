"""PyFDS domain model — FDS namelist entities and the ``FdsProject`` container.

Split by area from the former single ``model.py`` (plan step G2); every public
name is still importable from ``pyfds.domain.model``.
"""
from .base import Observer, FdsEntity, _MISSING
from .params import SimulationParams, DumpParams, MiscParams, PresParams, RadiParams
from .spatial import Mesh, Obstruction, Hole, Mult, Vent, Zone, Geom, MeshTransform, Move, PbrLook
from .physics import Layer, MaterialReaction, Material, Reaction, Surface, Ramp, Species, Particle
from .devices import Device, Prop, Control, Slice, Smoke3D, BoundaryFile, IsoSurface, Text, Prof, Plot3D
from .environment import Init, WindProfile
from .hvac import Hvac, HvacNode, HvacDuct, Fan, Damper, HvacFilter, HvacLeakage, HvacAircoil
from .project import FdsProject

__all__ = [
    "Observer",
    "FdsEntity",
    "SimulationParams",
    "DumpParams",
    "MiscParams",
    "PresParams",
    "RadiParams",
    "Mesh",
    "Obstruction",
    "Hole",
    "Mult",
    "Vent",
    "Zone",
    "Geom",
    "PbrLook",
    "MeshTransform",
    "Move",
    "Layer",
    "MaterialReaction",
    "Material",
    "Reaction",
    "Surface",
    "Ramp",
    "Species",
    "Particle",
    "Device",
    "Prop",
    "Control",
    "Slice",
    "Smoke3D",
    "BoundaryFile",
    "IsoSurface",
    "Text",
    "Prof",
    "Plot3D",
    "Init",
    "WindProfile",
    "Hvac",
    "HvacNode",
    "HvacDuct",
    "Fan",
    "Damper",
    "HvacFilter",
    "HvacLeakage",
    "HvacAircoil",
    "FdsProject",
]
