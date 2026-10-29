"""Devices, controls and outputs: DEVC, CTRL, PROP, SLCF, SM3D, BNDF, ISOF, PROF, PL3D.

Mixin for ``FdsParser``: each ``_parse_<tag>`` turns one tokenised record into entities.
"""
from __future__ import annotations

import logging
from typing import Dict
from pyfds.domain.prof_orient import prof_direction
from pyfds.domain.model import FdsProject, Device, Control, Prop, Slice, BoundaryFile, IsoSurface, Smoke3D, Prof, Plot3D

logger = logging.getLogger(__name__)


class DeviceBuilders:
    def _parse_devc(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"DEVC_{len(p.devices)}")
        xyz = self._parse_xyz(d.get("XYZ", "0,0,0"))
        ori_str = d.get("ORIENTATION")
        ori = self._parse_xyz(ori_str) if ori_str else None
        # XB for spatial statistics (optional)
        xb_devc = None
        if "XB" in d:
            xb_devc = tuple(self._parse_xb(d["XB"]))
        p.add_entity(Device(
            name=name, quantity=self._str(d, "QUANTITY", "TEMPERATURE"),
            x=xyz[0], y=xyz[1], z=xyz[2], orientation=ori,
            prop_id=self._str(d, "PROP_ID") or None,
            ctrl_id=self._str(d, "CTRL_ID") or None,
            setpoint=self._flt(d, "SETPOINT"),
            latch=self._bool(d, "LATCH", True),
            statistics=self._str(d, "STATISTICS") or None,
            temporal_statistic=self._str(d, "TEMPORAL_STATISTIC") or None,
            no_update_ctrl_id=self._str(d, "NO_UPDATE_CTRL_ID") or None,
            no_update_devc_id=self._str(d, "NO_UPDATE_DEVC_ID") or None,
            # Phase 1 additions
            quantity2=self._str(d, "QUANTITY2") or None,
            duct_id=self._str(d, "DUCT_ID") or None,
            initial_state=self._bool(d, "INITIAL_STATE", False),
            trip_direction=self._int(d, "TRIP_DIRECTION", 1),
            # Extended DEVC fields
            xb=xb_devc,
            ior=self._int(d, "IOR"),
            surf_id=self._str(d, "SURF_ID") or None,
            conversion_factor=self._flt(d, "CONVERSION_FACTOR"),
            smoothed_data=self._bool(d, "SMOOTHED_DATA"),
            hide_coordinates=self._bool(d, "HIDE_COORDINATES"),
            pipe_index=self._int(d, "PIPE_INDEX"),
            spec_id=self._str(d, "SPEC_ID") or None,
            devc_id=self._str(d, "DEVC_ID") or None,
            flowrate=self._flt(d, "FLOWRATE"),
            delay=self._flt(d, "DELAY"),
            bypass_flowrate=self._flt(d, "BYPASS_FLOWRATE"),
            node_id=self._strs(d, "NODE_ID"),
            cell_l=self._flt(d, "CELL_L"),
            relative=self._bool(d, "RELATIVE"),
        ))

    def _parse_slcf(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"SLCF_{len(p.slices)}")
        qty = self._str(d, "QUANTITY", "TEMPERATURE")
        # 3D volumetric slice uses XB; planar slice uses PBX/PBY/PBZ
        xb_3d = None
        if "XB" in d:
            xb_3d = tuple(self._parse_xb(d["XB"]))
        plane = "X"
        pos = 0.0
        for ax in ["X", "Y", "Z"]:
            key = f"PB{ax}"
            if key in d:
                plane = ax
                pos = float(d[key])
                break
        p.add_entity(Slice(name=name, quantity=qty, plane=plane, position=pos,
                           xb=xb_3d,
                           vector=self._bool(d, "VECTOR"),
                           cell_centered=self._bool(d, "CELL_CENTERED"),
                           spec_id=self._str(d, "SPEC_ID") or None))

    def _parse_sm3d(self, p: FdsProject, d: Dict) -> None:
        p.add_entity(Smoke3D(
            name=self._str(d, "ID", f"SM3D_{len(p.smoke3ds)}"),
            quantity=self._str(d, "QUANTITY", "DENSITY"),
            spec_id=self._str(d, "SPEC_ID") or None))

    def _parse_bndf(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"BNDF_{len(p.bndfs)}")
        p.add_entity(BoundaryFile(name=name,
                                   quantity=self._str(d, "QUANTITY", "WALL TEMPERATURE")))

    def _parse_isof(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"ISOF_{len(p.isofs)}")
        p.add_entity(IsoSurface(name=name,
                                 quantity=self._str(d, "QUANTITY", "TEMPERATURE"),
                                 value=self._flt(d, "VALUE", 100.0)))

    def _parse_ctrl(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"CTRL_{len(p.controls)}")
        # INPUT_IDS may be comma-separated
        input_ids_raw = d.get("INPUT_ID")
        input_ids = None
        if input_ids_raw:
            input_ids = [v.strip().strip("'\"") for v in input_ids_raw.split(",")]
        # Phase 1: parse DEADBAND
        deadband = None
        db_raw = d.get("DEADBAND")
        if db_raw:
            try:
                db_vals = [float(v.strip()) for v in db_raw.split(",")]
                if len(db_vals) == 2:
                    deadband = (db_vals[0], db_vals[1])
            except (ValueError, TypeError):
                pass
        p.add_entity(Control(
            name=name,
            function_type=self._str(d, "FUNCTION_TYPE", "CUSTOM"),
            input_id=self._str(d, "INPUT_ID") or None,
            input_ids=input_ids,
            setpoint=self._flt(d, "SETPOINT"),
            delay=self._flt(d, "DELAY", 0.0),
            latch=self._bool(d, "LATCH", True),
            initial_state=self._bool(d, "INITIAL_STATE", False),
            on_bound=self._str(d, "ON_BOUND", "LOWER"),
            n=self._int(d, "N"),
            # Phase 1 additions
            deadband=deadband,
            percentile_rank=self._flt(d, "PERCENTILE") if "PERCENTILE" in d else self._flt(d, "PERCENTILE_RANK"),
            ramp_id=self._str(d, "RAMP_ID") or None,
            constant=self._flt(d, "CONSTANT"),
            target_value=self._flt(d, "TARGET_VALUE"),
            proportional_gain=self._flt(d, "PROPORTIONAL_GAIN"),
            integral_gain=self._flt(d, "INTEGRAL_GAIN"),
            differential_gain=self._flt(d, "DIFFERENTIAL_GAIN"),
        ))

    def _parse_prop(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"PROP_{len(p.props)}")
        spray = self._floats(d, "SPRAY_ANGLE")
        sv_params = self._indexed(d, "SMOKEVIEW_PARAMETERS", str)
        p.add_entity(Prop(
            name=name,
            quantity=self._str(d, "QUANTITY") or None,
            part_id=self._str(d, "PART_ID") or None,
            rti=self._flt(d, "RTI", 50.0),
            c_factor=self._flt(d, "C_FACTOR", 0.7),
            operating_pressure=self._flt(d, "OPERATING_PRESSURE"),
            offset=self._flt(d, "OFFSET", 0.1),
            activation_obscuration=self._flt(d, "ACTIVATION_OBSCURATION"),
            activation_temperature=self._flt(d, "ACTIVATION_TEMPERATURE"),
            initial_temperature=self._flt(d, "INITIAL_TEMPERATURE"),
            spray_angle=(spray[0], spray[1]) if spray and len(spray) == 2 else None,
            flow_rate=self._flt(d, "FLOW_RATE"),
            particle_velocity=self._flt(d, "PARTICLE_VELOCITY"),
            characteristic_velocity=self._flt(d, "CHARACTERISTIC_VELOCITY"),
            length=self._flt(d, "LENGTH"),
            smokeview_id=self._str(d, "SMOKEVIEW_ID") or None,
            smokeview_parameters=sv_params or None,
            k_factor=self._flt(d, "K_FACTOR"),
            orifice_diameter=self._flt(d, "ORIFICE_DIAMETER"),
            pressure_ramp=self._str(d, "PRESSURE_RAMP") or None,
            fed_activity=self._int(d, "FED_ACTIVITY"),
        ))

    def _parse_prof(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"PROF_{len(p.profs)}")
        xyz = self._parse_xyz(d.get("XYZ", "0,0,0"))
        p.add_entity(Prof(name=name, quantity=self._str(d, "QUANTITY", "INSIDE WALL TEMPERATURE"),
                          x=xyz[0], y=xyz[1], z=xyz[2],
                          direction=prof_direction(d)))

    def _parse_pl3d(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"PL3D_{len(p.plot3ds)}")
        p.add_entity(Plot3D(
            name=name,
            quantity=self._str(d, "QUANTITY", "TEMPERATURE"),
            velo_index=self._int(d, "VELO_INDEX"),
            spec_id=self._str(d, "SPEC_ID") or None,
        ))
