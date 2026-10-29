"""Spatial namelists: MESH, OBST, HOLE, MULT, VENT, ZONE, GEOM, TRN*, MOVE.

Mixin for ``FdsParser``: each ``_parse_<tag>`` turns one tokenised record into entities.
"""
from __future__ import annotations

import logging
from typing import Dict
from pyfds.domain.model import FdsProject, Mesh, Obstruction, Hole, Mult, Vent, Zone, Geom, MeshTransform, Move

logger = logging.getLogger(__name__)


class SpatialBuilders:
    def _parse_mesh(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"MESH_{len(p.meshes)}")
        xb = self._parse_xb(d.get("XB", "0,1,0,1,0,1"), ordered=True)
        ijk = self._parse_ijk(d.get("IJK", "10,10,10"))
        mpi = self._int(d, "MPI_PROCESS")
        if mpi is None:                      # 0 is a valid rank, so no `or`
            mpi = self._int(d, "MPI_PROCESSOR")
        cylindrical = self._bool(d, "CYLINDRICAL")   # Phase 1 addition
        p.add_entity(Mesh(name=name, x_min=xb[0], x_max=xb[1],
                          y_min=xb[2], y_max=xb[3], z_min=xb[4], z_max=xb[5],
                          cell_count=ijk, mpi_processor=mpi,
                          cylindrical=cylindrical, mult_id=self._str(d, "MULT_ID") or None,
                          color=self._str(d, "COLOR") or None))

    def _apply_default_surface(self, project) -> None:
        """An &OBST with no SURF_ID is made of the &SURF that says DEFAULT=.TRUE. (INERT when there is none): say so explicitly,
        so the model shows (and writes back) what FDS will use."""
        names = self.__dict__.pop("_obst_without_surface", [])
        no_color = set(self.__dict__.pop("_obst_without_color", []))
        default = next((s for s in project.surfaces
                        if str((s.fds_extra or {}).get("DEFAULT", "")).strip().upper() in (".TRUE.", "T", ".T.", "TRUE")), None)
        for o in project.obstructions:
            if default is not None and o.name in names:
                o.surface_id = default.name
            if o.name in no_color:                         # FDS draws such an object in its surface's colour
                surf = next((s for s in project.surfaces if s.name == o.surface_id), None)
                if surf is not None and getattr(surf, "rgb", None):
                    o.rgb = tuple(surf.rgb)
                elif surf is not None and surf.color:
                    o.color = surf.color

    def _parse_obst(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"OBST_{len(p.obstructions)}")
        xb = self._parse_xb(d.get("XB", "0,1,0,1,0,1"))
        surf_id = self._str(d, "SURF_ID", "INERT")
        if "SURF_ID" not in d and "SURF_IDS" not in d and "SURF_ID6" not in d:
            self.__dict__.setdefault("_obst_without_surface", []).append(name)      # takes the DEFAULT surface once all SURFs are read
        if "COLOR" not in d and "RGB" not in d:
            self.__dict__.setdefault("_obst_without_color", []).append(name)        # shows its surface's colour (as in FDS)
        # SURF_IDS = (top, sides, bottom); SURF_ID6 = one per face. Stored in file order.
        surf_ids = self._str_list(d, "SURF_ID6") or self._str_list(d, "SURF_IDS")
        if surf_ids is not None and len(surf_ids) not in (3, 6):
            # e.g. SURF_IDS='FIRE' (top only): FDS fills the other faces from SURF_ID, so the text is written back as is
            self.warnings.append(f"&OBST ID={name!r}: SURF_IDS/SURF_ID6 with {len(surf_ids)} entries kept as written")
            self._unread(d, "SURF_ID6")
            self._unread(d, "SURF_IDS")
            surf_ids = None
        rgb = self._floats(d, "RGB")
        tex = self._floats(d, "TEXTURE_ORIGIN")
        p.add_entity(Obstruction(
            name=name, x_min=xb[0], x_max=xb[1],
            y_min=xb[2], y_max=xb[3], z_min=xb[4], z_max=xb[5],
            surface_id=surf_id,
            surface_ids=surf_ids,
            color=self._str(d, "COLOR", "GRAY"),
            thicken=self._bool(d, "THICKEN"),
            allow_vent=self._bool(d, "ALLOW_VENT"),
            transparency=self._flt(d, "TRANSPARENCY", 0.0),
            mult_id=self._str(d, "MULT_ID") or None,
            ctrl_id=self._str(d, "CTRL_ID") or None,
            devc_id=self._str(d, "DEVC_ID") or None,
            rgb=tuple(int(v) for v in rgb) if rgb and len(rgb) == 3 else None,
            texture_origin=tuple(tex) if tex and len(tex) == 3 else None,
            permit_hole=self._opt_bool(d, "PERMIT_HOLE"),
            removable=self._opt_bool(d, "REMOVABLE"),
            bulk_density=self._flt(d, "BULK_DENSITY"),
        ))

    def _parse_hole(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"HOLE_{len(p.holes)}")
        xb = self._parse_xb(d.get("XB", "0,1,0,1,0,1"))
        p.add_entity(Hole(name=name, x_min=xb[0], x_max=xb[1],
                          y_min=xb[2], y_max=xb[3], z_min=xb[4], z_max=xb[5]))

    def _parse_mult(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"MULT_{len(p.mults)}")
        p.add_entity(Mult(
            name=name,
            dx=self._flt(d, "DX", 0.0),
            dy=self._flt(d, "DY", 0.0),
            dz=self._flt(d, "DZ", 0.0),
            # Phase 1 fix: parse DX0/DY0/DZ0
            dx0=self._flt(d, "DX0", 0.0),
            dy0=self._flt(d, "DY0", 0.0),
            dz0=self._flt(d, "DZ0", 0.0),
            i_lower=self._int(d, "I_LOWER", 0),
            i_upper=self._int(d, "I_UPPER", 0),
            j_lower=self._int(d, "J_LOWER", 0),
            j_upper=self._int(d, "J_UPPER", 0),
            k_lower=self._int(d, "K_LOWER", 0),
            k_upper=self._int(d, "K_UPPER", 0),
        ))

    def _parse_vent(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"VENT_{len(p.vents)}")
        xb = self._parse_xb(d.get("XB", "0,1,0,1,0,1"))
        # UVW — velocity vector
        uvw_str = d.get("UVW")
        uvw = None
        if uvw_str:
            try:
                parts = [float(x) for x in str(uvw_str).split(",")]
                if len(parts) == 3:
                    uvw = tuple(parts)
            except (ValueError, TypeError):
                pass
        p.add_entity(Vent(name=name, x_min=xb[0], x_max=xb[1],
                          y_min=xb[2], y_max=xb[3], z_min=xb[4], z_max=xb[5],
                          surface_id=self._str(d, "SURF_ID", "OPEN"),
                          ctrl_id=self._str(d, "CTRL_ID") or None,
                          # Extended VENT fields
                          ior=self._int(d, "IOR"),
                          uvw=uvw,
                          spread_rate=self._flt(d, "SPREAD_RATE"),
                          tmp_exterior=self._flt(d, "TMP_EXTERIOR"),
                          ))

    def _parse_zone(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"ZONE_{len(p.zones)}")
        xb = self._parse_xb(d.get("XB", "0,1,0,1,0,1"))
        leak_areas = self._floats(d, "LEAK_AREAS")                        # older PyFDS files
        if leak_areas is None:
            found = {}
            for k in range(0, 11):
                v = self._flt(d, f"LEAK_AREA({k})")
                if v is not None:
                    found[k] = v
            if found:
                leak_areas = [found.get(k, 0.0) for k in range(max(found) + 1)]
        # Parse XYZ interior point (preferred FDS form)
        xyz_interior = None
        if "XYZ" in d:
            try:
                xyz_interior = self._parse_xyz(d["XYZ"])
            except (TypeError, ValueError, IndexError):
                self.warnings.append(f"&ZONE {name!r}: XYZ={d['XYZ']!r} is not three numbers; the zone point was not kept")
        p.add_entity(Zone(name=name, x_min=xb[0], x_max=xb[1],
                          y_min=xb[2], y_max=xb[3], z_min=xb[4], z_max=xb[5],
                          xyz=xyz_interior,
                          leak_areas=leak_areas))

    def _parse_geom(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"GEOM_{len(p.geoms)}")
        # Parse vertex flat array → list of (x, y, z) tuples
        verts = None
        flat_v = self._floats(d, "VERTS")
        if flat_v and len(flat_v) % 3 == 0:
            verts = [(flat_v[i], flat_v[i+1], flat_v[i+2])
                     for i in range(0, len(flat_v), 3)]
        # Parse face index flat array → list of (n1, n2, n3) tuples
        # Only plain vertex triplets are modelled. FACES with a 4th (surface
        # index) entry per face is left unread so it is carried through as-is.
        faces = None
        raw_faces = dict.get(d, "FACES")          # peek: does not mark the key as read
        multi_surface = "," in self._str(d, "SURF_ID", "")
        n_face_vals = len([v for v in (raw_faces or "").split(",") if v.strip()])
        if n_face_vals and not multi_surface and n_face_vals % 3 == 0 and n_face_vals % 4 != 0:
            flat_f = self._floats(d, "FACES")          # reading it marks the key as consumed
            if flat_f:
                faces = [(int(flat_f[i]), int(flat_f[i+1]), int(flat_f[i+2]))
                         for i in range(0, len(flat_f), 3)]
        p.add_entity(Geom(
            name=name,
            surf_id=self._str(d, "SURF_ID", "INERT"),
            is_terrain=self._bool(d, "IS_TERRAIN"),
            binary_file=self._str(d, "BINARY_FILE") or None,
            read_binary=self._bool(d, "READ_BINARY"),
            move_id=self._str(d, "MOVE_ID") or None,
            component_only=self._bool(d, "COMPONENT_ONLY"),
            verts=verts,
            faces=faces,
        ))

    def _parse_mesh_transform(self, p: FdsProject, d: Dict) -> None:
        # Direction is inferred from the original tag stored by the dispatch loop
        tag = d.get("_TAG", "TRNX")
        direction = tag[-1].upper() if tag.startswith("TRN") else "X"
        name = f"TRN{direction}_{len(p.mesh_transforms)}"
        p.add_entity(MeshTransform(
            name=name,
            direction=direction,
            mesh_number=self._int(d, "MESH_NUMBER", 1),
            ideriv=self._int(d, "IDERIV", 0),
            cc=self._flt(d, "CC", 0.0),
            pc=self._flt(d, "PC", 0.5),
        ))

    def _parse_move(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"MOVE_{len(p.moves)}")
        axis_str = d.get("AXIS", "0.0,0.0,1.0")
        try:
            axis = tuple(float(v.strip()) for v in axis_str.split(","))
            if len(axis) != 3:
                axis = (0.0, 0.0, 1.0)
        except Exception:
            axis = (0.0, 0.0, 1.0)
        vel_str = d.get("VELOCITY", "0.0,0.0,0.0")
        try:
            velocity = tuple(float(v.strip()) for v in vel_str.split(","))
            if len(velocity) != 3:
                velocity = (0.0, 0.0, 0.0)
        except Exception:
            velocity = (0.0, 0.0, 0.0)
        p.add_entity(Move(
            name=name,
            x0=self._flt(d, "X0", 0.0),
            y0=self._flt(d, "Y0", 0.0),
            z0=self._flt(d, "Z0", 0.0),
            axis=axis,
            omega=self._flt(d, "OMEGA", 0.0),
            velocity=velocity,
            rotation_angle=self._flt(d, "ROTATION_ANGLE"),
            dx=self._flt(d, "DX", 0.0),
            dy=self._flt(d, "DY", 0.0),
            dz=self._flt(d, "DZ", 0.0),
            scale=self._flt(d, "SCALE", 1.0),
        ))
