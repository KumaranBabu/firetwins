"""Real-solver check for the Edit Materials / Edit Surfaces work: what the editor writes for a material that matches a
rate curve, gives off gases and a residue material, and for typed surfaces, must be accepted by FDS 6.10 and survive a
write / read round trip. Skipped without ``fds_smv/``."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from pyfds.api import FdsApi
from pyfds.core.config import get_config
from pyfds.gui.editors.collection_editor import EntityCollectionEditor
from pyfds.io.fds_parser import FdsParser

HOME = Path(os.environ.get("PYFDS_FDS_HOME", Path(__file__).resolve().parents[2] / "fds_smv"))
FDS = HOME / "FDS6" / "bin" / "fds.exe"

pytestmark = pytest.mark.skipif(not FDS.exists(), reason="FDS not installed")


def test_editor_made_materials_and_surfaces_run_in_real_fds(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    cfg = get_config()
    saved = cfg.get("fds_binary")
    cfg.set("fds_binary", str(FDS))
    try:
        api = FdsApi()
        api.project.chid = "f5b"
        api.project.params.t_end = 0.3
        api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
        api.meshes.open_boundaries()
        api.reactions.add_simple_reaction("PROPANE", 46000.0, soot_yield=0.01)

        mats = EntityCollectionEditor(api, "materials", "Edit Materials")
        char = mats.new_object()
        wood = mats.new_object()
        wood_name = wood.name
        mats.field_widget("name").set_value("WOOD")
        mats.field_widget("density").set_value(500.0)
        mats.field_widget("heat_of_reaction").set_value(400.0)
        mats.field_widget("reference_temperature").set_value(350.0)
        mats.field_widget("heating_rate").set_value(10.0)
        mats.field_widget("pyrolysis_range").set_value(80.0)
        bw = mats._byproducts
        bw.add_gas("PROPANE", 0.7)
        bw.residue_yield.setText("0.2")
        bw.residue_material.setCurrentText(char.name)
        mats.apply()
        assert wood_name != "WOOD" and api.materials.get("WOOD") is wood
        mats.close()

        surfs = EntityCollectionEditor(api, "surfaces", "Edit Surfaces")
        layered = surfs.new_object()
        surfs._on_type_chosen(surfs.type_combo.findData("layered"))
        surfs.field_widget("name").set_value("WOOD WALL")
        surfs.field_widget("layers").add_row({"material_id": "WOOD", "thickness": 0.02})
        surfs.apply()
        burner = surfs.new_object()
        surfs._on_type_chosen(surfs.type_combo.findData("burner"))
        surfs.field_widget("name").set_value("FIRE")
        surfs.field_widget("heat_release_rate").set_value(500.0)
        surfs.apply()
        surfs.close()
        assert api.surfaces.kind("WOOD WALL") == "layered" and api.surfaces.kind("FIRE") == "burner"

        api.obstructions.add_obstruction([0.2, 0.5, 0.2, 0.5, 0.0, 0.3], "WOOD WALL", name="WALL")
        api.vents.add_vent([0.7, 0.9, 0.7, 0.9, 0.0, 0.0], "FIRE")
        errors = [r for r in api.validation.validate().results
                  if r.severity.name.upper().startswith("ERR") and r.rule != "FireResolution"]   # a coarse test mesh
        assert not errors

        h = api.solvers.run_local(str(tmp_path), validate_first=False)
        assert api.solvers.wait(h, 300) and api.solvers.status(h) == "done", h.message

        back = FdsParser().parse_string(api.fds_text())
        w = next(m for m in back.materials if m.name == "WOOD")
        assert (w.heating_rate, w.pyrolysis_range, w.residue_id, w.nu_residue, w.spec_ids, w.nu_gases) == (
            10.0, 80.0, char.name, 0.2, ["PROPANE"], [0.7])
    finally:
        cfg.set("fds_binary", saved)
