"""Unit tests — Phase 4 & 5: (part 2 of 3)."""


from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_obst(name="wall", x=(0, 1), y=(0, 4), z=(0, 3)):
    from pyfds.domain.model import Obstruction
    return Obstruction(
        name=name,
        x_min=x[0], x_max=x[1],
        y_min=y[0], y_max=y[1],
        z_min=z[0], z_max=z[1],
        surface_id="INERT",
    )

def _make_project():
    from pyfds.domain.model import FdsProject, Mesh
    p = FdsProject()
    p.chid = "test_case"
    p.add_entity(Mesh(
        name="m1", cell_count=(10, 10, 5),
        x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=2
    ))
    p.add_entity(_make_obst())
    return p


class TestMirrorCommand:

    def test_mirror_x_axis(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(1, 3), y=(0, 4), z=(0, 2))
        cmd = MirrorCommand(obst, axis=0, position=0.0)
        cmd.execute()
        assert obst.x_min == pytest.approx(-3.0)
        assert obst.x_max == pytest.approx(-1.0)
        assert obst.y_min == pytest.approx(0.0)

    def test_mirror_y_axis(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(0, 2), y=(1, 3), z=(0, 2))
        cmd = MirrorCommand(obst, axis=1, position=0.0)
        cmd.execute()
        assert obst.y_min == pytest.approx(-3.0)
        assert obst.y_max == pytest.approx(-1.0)

    def test_mirror_z_axis(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(0, 2), y=(0, 2), z=(1, 3))
        cmd = MirrorCommand(obst, axis=2, position=0.0)
        cmd.execute()
        assert obst.z_min == pytest.approx(-3.0)
        assert obst.z_max == pytest.approx(-1.0)

    def test_mirror_centroid_default(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(0, 4), y=(0, 4), z=(0, 2))
        cmd = MirrorCommand(obst, axis=0)  # default pos = centroid x = 2.0
        cmd.execute()
        assert obst.x_min == pytest.approx(0.0)
        assert obst.x_max == pytest.approx(4.0)

    def test_mirror_undo_restores(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst(x=(1, 3), y=(0, 4), z=(0, 2))
        cmd = MirrorCommand(obst, axis=0, position=0.0)
        cmd.execute()
        cmd.undo()
        assert obst.x_min == pytest.approx(1.0)
        assert obst.x_max == pytest.approx(3.0)

    def test_invalid_axis_raises(self):
        from pyfds.automation.commands import MirrorCommand
        obst = _make_obst()
        with pytest.raises(ValueError, match="axis"):
            MirrorCommand(obst, axis=3)

    def test_mirror_via_pipeline(self):
        from pyfds.automation.commands import MirrorCommand, CommandPipeline
        p = _make_project()
        pipe = CommandPipeline(p)
        obst = _make_obst(x=(1, 3), y=(0, 4), z=(0, 2))
        p.add_entity(obst)
        result = pipe.execute(MirrorCommand(obst, axis=0, position=0.0))
        assert result.success
        pipe.undo()
        assert obst.x_min == pytest.approx(1.0)

class TestRotateCommand:

    def test_rotate_180(self):
        from pyfds.automation.commands import RotateCommand
        # 1×1 box centred at (1,1) rotated 180° around origin (0,0)
        obst = _make_obst(x=(0.5, 1.5), y=(0.5, 1.5), z=(0, 2))
        cmd = RotateCommand(obst, degrees=180, origin=(0.0, 0.0))
        cmd.execute()
        assert obst.x_min == pytest.approx(-1.5)
        assert obst.x_max == pytest.approx(-0.5)
        assert obst.y_min == pytest.approx(-1.5)
        assert obst.y_max == pytest.approx(-0.5)

    def test_rotate_90(self):
        from pyfds.automation.commands import RotateCommand
        # 1×2 box: x=(0,1), y=(0,2) rotated 90° CCW around (0,0)
        obst = _make_obst(x=(0, 1), y=(0, 2), z=(0, 1))
        cmd = RotateCommand(obst, degrees=90, origin=(0.0, 0.0))
        cmd.execute()
        # After 90° CCW: (x,y) → (-y, x)
        # corners: (0,0)→(0,0), (1,0)→(0,1), (0,2)→(-2,0), (1,2)→(-2,1)
        assert obst.x_min == pytest.approx(-2.0)
        assert obst.x_max == pytest.approx(0.0)
        assert obst.y_min == pytest.approx(0.0)
        assert obst.y_max == pytest.approx(1.0)

    def test_rotate_z_unchanged(self):
        from pyfds.automation.commands import RotateCommand
        obst = _make_obst(z=(1, 3))
        cmd = RotateCommand(obst, degrees=180, origin=(0.0, 0.0))
        cmd.execute()
        assert obst.z_min == pytest.approx(1.0)
        assert obst.z_max == pytest.approx(3.0)

    def test_rotate_undo(self):
        from pyfds.automation.commands import RotateCommand
        obst = _make_obst(x=(0.5, 1.5), y=(0.5, 1.5), z=(0, 2))
        cmd = RotateCommand(obst, degrees=90, origin=(0.0, 0.0))
        cmd.execute()
        cmd.undo()
        assert obst.x_min == pytest.approx(0.5)
        assert obst.x_max == pytest.approx(1.5)

    def test_rotate_non_multiple_of_90_raises(self):
        from pyfds.automation.commands import RotateCommand
        obst = _make_obst()
        with pytest.raises(ValueError, match="multiple of 90"):
            RotateCommand(obst, degrees=45)

    def test_rotate_default_origin_centroid(self):
        from pyfds.automation.commands import RotateCommand
        # Square centred at (2,2) — rotating 360° = identity
        obst = _make_obst(x=(1, 3), y=(1, 3), z=(0, 1))
        cmd = RotateCommand(obst, degrees=360)
        cmd.execute()
        assert obst.x_min == pytest.approx(1.0)
        assert obst.x_max == pytest.approx(3.0)

class TestFloorManager:

    def test_define_floor(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        f = api.floors.define_floor("Ground", 0.0, 3.0)
        assert f.name == "Ground"
        assert f.z_min == 0.0
        assert f.z_max == 3.0

    def test_all_floors_sorted_by_z(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Level 2", 6.0, 9.0)
        api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.define_floor("Level 1", 3.0, 6.0)
        names = [f.name for f in api.floors.all_floors()]
        assert names == ["Ground", "Level 1", "Level 2"]

    def test_get_floor(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        assert api.floors.get_floor("Ground") is not None
        assert api.floors.get_floor("Roof") is None

    def test_delete_floor(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.delete_floor("Ground")
        assert api.floors.get_floor("Ground") is None

    def test_floor_of_by_bbox(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        obst = _make_obst(z=(0, 2))   # z-centre = 1.0 → Ground
        f = api.floors.floor_of(obst)
        assert f is not None
        assert f.name == "Ground"

    def test_floor_of_no_match(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        obst = _make_obst(z=(5, 8))   # z-centre = 6.5 — outside Ground
        assert api.floors.floor_of(obst) is None

    def test_floor_of_surface_returns_none(self):
        from pyfds.api.controller import FdsApi
        from pyfds.domain.model import Surface
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        s = Surface(name="inert")
        assert api.floors.floor_of(s) is None

    def test_entities_on_floor(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        obst = api.obstructions.add_obstruction(
            xb=[0, 1, 0, 1, 0, 2], surf_id="INERT", name="ground_obst"
        )
        entities = api.floors.entities_on_floor("Ground")
        assert any(e.name == "ground_obst" for e in entities)

    def test_assign_and_floor_of(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        obst = _make_obst(z=(10, 12))   # outside ground by bbox
        api.floors.assign(obst, "Ground")
        f = api.floors.floor_of(obst)
        assert f.name == "Ground"

    def test_assign_unknown_floor_raises(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = _make_obst()
        with pytest.raises(KeyError):
            api.floors.assign(obst, "NonExistent")

    def test_auto_assign_all(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        api.obstructions.add_obstruction(
            xb=[0, 1, 0, 1, 0, 2], surf_id="INERT", name="low_obst"
        )
        count = api.floors.auto_assign_all()
        assert count > 0

    def test_repr(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Ground", 0.0, 3.0)
        assert "Ground" in repr(api.floors)

    def test_all_alias_matches_all_floors(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.floors.define_floor("Level 1", 3.0, 6.0)
        api.floors.define_floor("Ground", 0.0, 3.0)
        assert api.floors.all() == api.floors.all_floors()

    def test_remove_alias_deletes_by_entity_name(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        f = api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.remove(f)
        assert api.floors.get_floor("Ground") is None

    def test_export_then_import_floors_rematches_by_entity_name(self, tmp_path):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ground_box")
        api.floors.define_floor("Ground", 0.0, 3.0, "ground floor")
        api.floors.define_floor("Level 1", 3.0, 6.0)
        api.floors.assign(obst, "Ground")

        path = tmp_path / "floors.json"
        api.floors.export_floors(str(path))
        assert path.exists()

        # A brand-new project/api — a fresh entity with the same NAME but a
        # different uid, simulating a save/reload round trip.
        api2 = FdsApi()
        obst2 = api2.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ground_box")
        assert obst2.uid != obst.uid

        count = api2.floors.import_floors(str(path))

        assert count == 1
        assert [f.name for f in api2.floors.all_floors()] == ["Ground", "Level 1"]
        assert api2.floors.floor_of(obst2).name == "Ground"

    def test_import_floors_skips_unmatched_assignments(self, tmp_path):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        obst = api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="ghost_box")
        api.floors.define_floor("Ground", 0.0, 3.0)
        api.floors.assign(obst, "Ground")
        path = tmp_path / "floors.json"
        api.floors.export_floors(str(path))

        api2 = FdsApi()  # no "ghost_box" entity here
        count = api2.floors.import_floors(str(path))

        assert count == 0
        assert api2.floors.get_floor("Ground") is not None
