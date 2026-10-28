"""FDS writer part: devices and output files (slices, boundary files, isosurfaces, Plot3D, profiles), zones, wind profiles."""
from __future__ import annotations

from typing import Any, Dict

from pyfds.domain.model import (
    Device,
    Slice,
    BoundaryFile,
    IsoSurface,
    Zone,
    Prof,
    Plot3D,
    WindProfile,
    Smoke3D,
)

from pyfds.domain.prof_orient import prof_ior
from .fds_writer_common import _nl

_HVAC_PREFIXES = ("DUCT ", "NODE ", "FAN ", "AIRCOIL ", "FILTER ")


def _no_xyz(obj) -> bool:
    """HVAC outputs take no XYZ and a bounded (XB) device that sits at the unset origin has none either."""
    if (obj.x, obj.y, obj.z) != (0.0, 0.0, 0.0):
        return False
    if getattr(obj, "xb", None) is not None:
        return True
    return bool((obj.duct_id or getattr(obj, "node_id", None)) and obj.quantity.startswith(_HVAC_PREFIXES))


class FdsWriterDevicesMixin:
    def _write_device(self, obj: Device) -> str:
        d: Dict[str, Any] = {
            "ID":       obj.name,
            "QUANTITY": obj.quantity,
        }
        # HVAC outputs and bounded (XB) devices take no XYZ
        if not _no_xyz(obj):
            d["XYZ"] = [obj.x, obj.y, obj.z]
        if obj.orientation:                 d["ORIENTATION"]   = list(obj.orientation)
        if obj.prop_id:                     d["PROP_ID"]       = obj.prop_id
        if obj.ctrl_id:                     d["CTRL_ID"]       = obj.ctrl_id
        if obj.setpoint is not None:        d["SETPOINT"]      = obj.setpoint
        if not obj.latch:                   d["LATCH"]         = obj.latch
        if obj.statistics:                  d["STATISTICS"]    = obj.statistics
        if obj.time_averaged:               d["TIME_AVERAGED"] = obj.time_averaged
        # Phase 1 additions
        if obj.quantity2:                   d["QUANTITY2"]     = obj.quantity2
        if obj.duct_id:                     d["DUCT_ID"]       = obj.duct_id
        # P0 fixes
        if getattr(obj, "initial_state", None) is not None:      d["INITIAL_STATE"]      = obj.initial_state
        if getattr(obj, "trip_direction", None) is not None:     d["TRIP_DIRECTION"]     = obj.trip_direction
        if getattr(obj, "spatial_statistic", None):              d["SPATIAL_STATISTIC"]  = obj.spatial_statistic
        if getattr(obj, "points", None) is not None:             d["POINTS"]             = obj.points
        # VD_TO_VD and SMOOTHED_DATA are not FDS keywords (FDS stops with ERROR 101); smoothing is TEMPORAL_STATISTIC='SMOOTHED'
        temporal = getattr(obj, "temporal_statistic", None) or ("SMOOTHED" if getattr(obj, "smoothed_data", False) else None)
        if temporal:                                             d["TEMPORAL_STATISTIC"] = temporal
        if getattr(obj, "no_update_ctrl_id", None):              d["NO_UPDATE_CTRL_ID"]  = obj.no_update_ctrl_id
        if getattr(obj, "no_update_devc_id", None):              d["NO_UPDATE_DEVC_ID"]  = obj.no_update_devc_id
        # Extended DEVC fields
        if getattr(obj, "xb", None) is not None:                 d["XB"]                 = list(obj.xb)
        if getattr(obj, "ior", None) is not None:                d["IOR"]                = obj.ior
        if getattr(obj, "surf_id", None):                        d["SURF_ID"]            = obj.surf_id
        if getattr(obj, "conversion_factor", None) is not None:  d["CONVERSION_FACTOR"]  = obj.conversion_factor
        if getattr(obj, "hide_coordinates", False):               d["HIDE_COORDINATES"]   = True
        if getattr(obj, "pipe_index", None) is not None:          d["PIPE_INDEX"]         = obj.pipe_index
        if getattr(obj, "spec_id", None):                         d["SPEC_ID"]            = obj.spec_id
        if getattr(obj, "devc_id", None):                         d["DEVC_ID"]            = obj.devc_id
        if getattr(obj, "flowrate", None) is not None:            d["FLOWRATE"]           = obj.flowrate
        if getattr(obj, "delay", None) is not None:               d["DELAY"]              = obj.delay
        if getattr(obj, "bypass_flowrate", None) is not None:     d["BYPASS_FLOWRATE"]    = obj.bypass_flowrate
        if getattr(obj, "node_id", None):                         d["NODE_ID"]            = list(obj.node_id)
        if getattr(obj, "cell_l", None) is not None:              d["CELL_L"]             = obj.cell_l
        if getattr(obj, "relative", False):                       d["RELATIVE"]           = True
        return _nl("DEVC", d)

    def _write_slice(self, obj: Slice) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "QUANTITY": obj.quantity}
        # 3D volumetric slice uses XB; planar slice uses PBX/PBY/PBZ
        if getattr(obj, "xb", None) is not None:
            d["XB"] = list(obj.xb)
        else:
            d[f"PB{obj.plane.upper()}"] = obj.position
        if obj.vector:        d["VECTOR"]       = obj.vector
        if obj.cell_centered: d["CELL_CENTERED"] = obj.cell_centered
        if obj.quantity2:     d["QUANTITY2"]    = obj.quantity2
        if getattr(obj, "spec_id", None): d["SPEC_ID"] = obj.spec_id
        return _nl("SLCF", d)

    def _write_smoke3d(self, obj: Smoke3D) -> str:
        return _nl("SM3D", {"QUANTITY": obj.quantity, "SPEC_ID": obj.spec_id})

    def _write_bndf(self, obj: BoundaryFile) -> str:
        d: Dict[str, Any] = {"QUANTITY": obj.quantity}
        if obj.cell_centered: d["CELL_CENTERED"] = obj.cell_centered
        return _nl("BNDF", d)

    def _write_isof(self, obj: IsoSurface) -> str:
        # &ISOF has no ID (FDS 6.10 rejects it) and takes VALUE(1), VALUE(2) ...; the name is editor-side only
        d: Dict[str, Any] = {"QUANTITY": obj.quantity, "VALUE(1)": obj.value}
        if obj.quantity2:          d["QUANTITY2"] = obj.quantity2
        return _nl("ISOF", d)

    def _write_prof(self, obj: Prof) -> str:
        return _nl("PROF", {"ID": obj.name, "QUANTITY": obj.quantity,
                             "XYZ": [obj.x, obj.y, obj.z],
                             "IOR": prof_ior(obj.direction)})

    def _write_plot3d(self, obj: Plot3D) -> str:
        """Write &PL3D namelist."""
        d: Dict[str, Any] = {"ID": obj.name, "QUANTITY": obj.quantity}
        if obj.velo_index is not None: d["VELO_INDEX"] = obj.velo_index
        if obj.spec_id:                d["SPEC_ID"]    = obj.spec_id
        return _nl("PL3D", d)

    def _write_zone(self, obj: Zone) -> str:
        d: Dict[str, Any] = {"ID": obj.name}
        # FDS &ZONE requires a single interior XYZ point, not XB bounds.
        # Use xyz when set; fall back to centroid of the stored bounding box.
        if getattr(obj, "xyz", None) is not None:
            d["XYZ"] = list(obj.xyz)
        else:
            cx = (obj.x_min + obj.x_max) / 2.0
            cy = (obj.y_min + obj.y_max) / 2.0
            cz = (obj.z_min + obj.z_max) / 2.0
            d["XYZ"] = [cx, cy, cz]
        for other, area in enumerate(obj.leak_areas or []):          # LEAK_AREA(n): leakage to zone n (0 = outside)
            d[f"LEAK_AREA({other})"] = area
        return _nl("ZONE", d)

    def _write_wind_profile(self, obj: WindProfile) -> str:
        """Write &WIND namelist — atmospheric boundary layer profile."""
        d: Dict[str, Any] = {
            "SPEED":     obj.speed,
            "DIRECTION": obj.direction,
            "Z_REF":     obj.z_ref,
        }
        # FDS 6.10.1 names (verified against the real solver): Z_0, RAMP_SPEED_T, RAMP_DIRECTION_T.
        # Z0, RAMP_ID, USTAR and L_INF are rejected by it, so ustar/l_inf are model-only.
        if obj.z0 is not None:       d["Z_0"]      = obj.z0
        if obj.l is not None:        d["L"]        = obj.l
        if obj.ramp_id:              d["RAMP_SPEED_T"]     = obj.ramp_id
        if obj.ramp_direction:       d["RAMP_DIRECTION_T"] = obj.ramp_direction
        if obj.latitude is not None: d["LATITUDE"] = obj.latitude
        if obj.ground_level is not None:  d["GROUND_LEVEL"]  = obj.ground_level
        if obj.lapse_rate is not None:    d["LAPSE_RATE"]    = obj.lapse_rate
        if obj.stratification is not None: d["STRATIFICATION"] = obj.stratification
        if obj.theta_star is not None:    d["THETA_STAR"]    = obj.theta_star
        p = getattr(self, "_project", None)
        if p is not None and self._requires(p, "6.9"):
            first = next((w for w in p.wind_profiles if getattr(w, "enabled", True)), None)
            if first is obj:                                   # the initial wind field shares FDS's only &WIND line
                d.update({k.upper(): getattr(p.misc, k) for k in ("u0", "v0", "w0") if getattr(p.misc, k) != 0.0})
        return _nl("WIND", d)
