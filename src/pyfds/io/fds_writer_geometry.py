"""FDS writer part: meshes, obstructions, holes, vents, init regions, particles, geoms and transforms."""
from __future__ import annotations

from typing import Any, Dict

from pyfds.domain.model import Mesh, Obstruction, Hole, Mult, Vent, Particle, Init, Geom, MeshTransform, Move

from .fds_writer_common import _nl


class FdsWriterGeometryMixin:
    def _write_mesh(self, obj: Mesh) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XB": self._xb(obj),
                             "IJK": list(obj.cell_count)}
        if obj.mpi_processor is not None: d["MPI_PROCESS"] = obj.mpi_processor
        if obj.color:                     d["COLOR"]       = obj.color
        if obj.cylindrical:               d["CYLINDRICAL"] = obj.cylindrical
        return _nl("MESH", d)

    def _write_obst(self, obj: Obstruction) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XB": self._xb(obj)}
        if obj.surface_ids:
            # 3 entries = (top, sides, bottom) -> SURF_IDS; 6 = one per face -> SURF_ID6
            d["SURF_ID6" if len(obj.surface_ids) == 6 else "SURF_IDS"] = obj.surface_ids
        else:
            d["SURF_ID"] = obj.surface_id
        d["COLOR"]       = obj.color
        if obj.transparency: d["TRANSPARENCY"] = obj.transparency
        if obj.thicken:      d["THICKEN"]      = obj.thicken
        if obj.allow_vent:   d["ALLOW_VENT"]   = obj.allow_vent
        if obj.ctrl_id:      d["CTRL_ID"]      = obj.ctrl_id
        if obj.devc_id:      d["DEVC_ID"]      = obj.devc_id
        if obj.mult_id:      d["MULT_ID"]      = obj.mult_id
        if obj.rgb:             d["RGB"]            = list(obj.rgb)
        if obj.texture_origin:  d["TEXTURE_ORIGIN"] = list(obj.texture_origin)
        if obj.permit_hole is not None:   d["PERMIT_HOLE"]  = obj.permit_hole
        if obj.removable is not None:     d["REMOVABLE"]    = obj.removable
        if obj.bulk_density is not None:  d["BULK_DENSITY"] = obj.bulk_density
        return _nl("OBST", d)

    def _write_hole(self, obj: Hole) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XB": self._xb(obj)}
        if obj.ctrl_id: d["CTRL_ID"] = obj.ctrl_id
        return _nl("HOLE", d)

    def _write_mult(self, obj: Mult) -> str:
        d: Dict[str, Any] = {
            "ID":      obj.name,
            "DX":      obj.dx, "DY": obj.dy, "DZ": obj.dz,
            "I_LOWER": obj.i_lower, "I_UPPER": obj.i_upper,
            "J_LOWER": obj.j_lower, "J_UPPER": obj.j_upper,
            "K_LOWER": obj.k_lower, "K_UPPER": obj.k_upper,
        }
        # DX0/DY0/DZ0 — offset of the first copy (Phase 1 fix)
        if obj.dx0 != 0.0: d["DX0"] = obj.dx0
        if obj.dy0 != 0.0: d["DY0"] = obj.dy0
        if obj.dz0 != 0.0: d["DZ0"] = obj.dz0
        return _nl("MULT", d)

    def _write_vent(self, obj: Vent) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XB": self._xb(obj),
                             "SURF_ID": obj.surface_id}
        if obj.ctrl_id: d["CTRL_ID"] = obj.ctrl_id
        if obj.color:   d["COLOR"]   = obj.color
        if obj.transparency: d["TRANSPARENCY"] = obj.transparency
        # P0 fixes
        if getattr(obj, "dynamic_pressure", None) is not None: d["DYNAMIC_PRESSURE"] = obj.dynamic_pressure
        if getattr(obj, "devc_id", None):                      d["DEVC_ID"]          = obj.devc_id
        if getattr(obj, "rgb", None):                          d["RGB"]              = list(obj.rgb)
        # Extended VENT fields
        if getattr(obj, "ior", None) is not None:              d["IOR"]              = obj.ior
        if getattr(obj, "uvw", None) is not None:              d["UVW"]              = list(obj.uvw)
        if getattr(obj, "spread_rate", None) is not None:      d["SPREAD_RATE"]      = obj.spread_rate
        if getattr(obj, "tmp_exterior", None) is not None:     d["TMP_EXTERIOR"]     = obj.tmp_exterior
        return _nl("VENT", d)

    def _write_init(self, obj: Init) -> str:
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.xyz_center is None:                # XYZ (point/shape centre) replaces XB
            d["XB"] = self._xb(obj)
        if obj.temperature is not None:   d["TEMPERATURE"]   = obj.temperature
        if obj.density is not None:       d["DENSITY"]       = obj.density
        # Multi-species takes priority over single spec_id/mass_fraction
        if getattr(obj, "spec_ids", None):
            d["SPEC_ID"]       = obj.spec_ids
            if getattr(obj, "mass_fractions", None):
                d["MASS_FRACTION"] = obj.mass_fractions
        else:
            if obj.spec_id:                   d["SPEC_ID"]       = obj.spec_id
            if obj.mass_fraction is not None: d["MASS_FRACTION"] = obj.mass_fraction
        if obj.part_id:                   d["PART_ID"]       = obj.part_id      # without it the cloud makes no particles
        if obj.n_particles is not None:   d["N_PARTICLES"]   = obj.n_particles
        # Phase 1 additions
        if obj.shape != "BLOCK":          d["SHAPE"]         = obj.shape
        if obj.radius is not None:        d["RADIUS"]        = obj.radius
        if obj.xyz_center is not None:    d["XYZ"]           = list(obj.xyz_center)
        return _nl("INIT", d)

    def _write_particle(self, obj: Particle) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "COLOR": obj.color,
                             "DIAMETER": obj.diameter,
                             "DRAG_LAW": obj.drag_law,
                             "SAMPLING_FACTOR": obj.sampling_factor}
        if not self._requires(self._project, "6.9"):          # FDS 6.10 rejects DENSITY on &PART
            d["DENSITY"] = obj.density
        if obj.prop_id: d["PROP_ID"] = obj.prop_id
        if obj.surf_id: d["SURF_ID"] = obj.surf_id
        if obj.age is not None: d["AGE"] = obj.age
        # P0 fixes — evaporation / droplet fields
        if getattr(obj, "spec_id", None):                              d["SPEC_ID"]                  = obj.spec_id
        if getattr(obj, "vaporization_temperature", None) is not None: d["VAPORIZATION_TEMPERATURE"] = obj.vaporization_temperature
        if getattr(obj, "heat_of_vaporization", None) is not None:    d["HEAT_OF_VAPORIZATION"]     = obj.heat_of_vaporization
        if getattr(obj, "n_strata", None) is not None:                 d["N_STRATA"]                 = obj.n_strata
        if getattr(obj, "gamma", None) is not None:                    d["GAMMA"]                    = obj.gamma
        if getattr(obj, "sigma", None) is not None:                    d["SIGMA"]                    = obj.sigma
        # New fields added in gap-fill
        if getattr(obj, "quantities", None):                           d["QUANTITIES"]               = obj.quantities
        if getattr(obj, "orientation", None):                          d["ORIENTATION"]              = list(obj.orientation)
        if getattr(obj, "ctrl_id", None):                              d["CTRL_ID"]                  = obj.ctrl_id
        for key, attr in (("MASSLESS", "massless"), ("STATIONARY", "stationary"), ("MONODISPERSE", "monodisperse"),
                          ("TARGET_ONLY", "target_only")):
            if getattr(obj, attr, False):
                d[key] = True
        for key, attr in (("INITIAL_TEMPERATURE", "initial_temperature"), ("MINIMUM_DIAMETER", "minimum_diameter"),
                          ("MAXIMUM_DIAMETER", "maximum_diameter"), ("FREE_AREA_FRACTION", "free_area_fraction"),
                          ("HORIZONTAL_VELOCITY", "horizontal_velocity"), ("VERTICAL_VELOCITY", "vertical_velocity")):
            if getattr(obj, attr, None) is not None:
                d[key] = getattr(obj, attr)
        return _nl("PART", d)

    def _write_geom(self, obj: Geom) -> str:
        """Write &GEOM namelist. Vertex/face arrays are written inline."""
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.surf_ids:                    d["SURF_ID"]     = obj.surf_ids
        else:                               d["SURF_ID"]     = obj.surf_id
        if obj.is_terrain:                  d["IS_TERRAIN"]  = obj.is_terrain
        if obj.binary_file:                 d["BINARY_FILE"] = obj.binary_file
        if obj.read_binary:                 d["READ_BINARY"] = obj.read_binary
        if obj.move_id:                     d["MOVE_ID"]     = obj.move_id
        if obj.component_only:              d["COMPONENT_ONLY"] = obj.component_only
        # Inline vertex and face arrays
        if obj.verts:
            # Flatten: VERTS=x1,y1,z1,x2,y2,z2,...
            flat = [c for v in obj.verts for c in v]
            d["VERTS"] = flat
        if obj.faces:
            # Flatten: FACES=n1,n2,n3,...
            flat_f = [i for f in obj.faces for i in f]
            d["FACES"] = flat_f
        return _nl("GEOM", d)

    def _write_mesh_transform(self, obj: MeshTransform) -> str:
        """Write &TRNX/TRNY/TRNZ namelist."""
        tag = f"TRN{obj.direction.upper()}"
        d: Dict[str, Any] = {
            "MESH_NUMBER": obj.mesh_number,
            "IDERIV":      obj.ideriv,
            "CC":          obj.cc,
            "PC":          obj.pc,
        }
        return _nl(tag, d)

    def _write_move(self, obj: Move) -> str:
        """Write &MOVE namelist — rigid body motion."""
        d: Dict[str, Any] = {"ID": obj.name}
        if obj.x0 != 0.0 or obj.y0 != 0.0 or obj.z0 != 0.0:
            d["X0"] = obj.x0; d["Y0"] = obj.y0; d["Z0"] = obj.z0
        ax = list(obj.axis)
        if ax != [0.0, 0.0, 1.0]: d["AXIS"] = ax
        if obj.omega != 0.0:  d["OMEGA"]    = obj.omega
        vel = list(obj.velocity)
        if vel != [0.0, 0.0, 0.0]: d["VELOCITY"] = vel
        if obj.rotation_angle is not None: d["ROTATION_ANGLE"] = obj.rotation_angle
        if obj.dx != 0.0: d["DX"] = obj.dx
        if obj.dy != 0.0: d["DY"] = obj.dy
        if obj.dz != 0.0: d["DZ"] = obj.dz
        if obj.scale != 1.0: d["SCALE"] = obj.scale
        return _nl("MOVE", d)
