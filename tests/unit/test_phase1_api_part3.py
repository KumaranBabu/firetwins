"""Unit tests — Phase 1 API additions. (part 3 of 3)."""


from __future__ import annotations

import math
import time
import pytest


class TestValidationAutoFix:
    def test_auto_fix_returns_report(self):
        from pyfds.api.controller import FdsApi
        from pyfds.domain.model import Mesh
        api = FdsApi()
        api.project.add_entity(
            Mesh(name="M", cell_count=(10, 10, 10),
                 x_min=0, x_max=1, y_min=0, y_max=1, z_min=0, z_max=1)
        )
        report = api.validation.auto_fix()
        assert hasattr(report, "results") and hasattr(report, "errors")

    def test_auto_fix_does_not_raise_on_clean_project(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        report = api.validation.auto_fix()
        assert report is not None

class TestExecutionRunAsync:
    def test_run_async_returns_future(self):
        from pyfds.api.controller import FdsApi
        import concurrent.futures
        api = FdsApi()
        future = api.execution.run_async(output_dir="tmp_async_test")
        assert isinstance(future, concurrent.futures.Future)

class TestCLIAutofix:
    def test_autofix_missing_file(self, tmp_path):
        from pyfds.cli.main import main
        rc = main(["autofix", str(tmp_path / "nonexistent.fds")])
        assert rc == 1

    def test_autofix_invalid_project(self, tmp_path):
        bad = tmp_path / "bad.fds"
        bad.write_text("&RUBBISH /\n", encoding="utf-8")
        from pyfds.cli.main import main
        # Parser may raise or succeed; just confirm no unhandled exception
        try:
            rc = main(["autofix", str(bad)])
        except SystemExit as exc:
            rc = exc.code
        assert isinstance(rc, int)

class TestCLISchema:
    def test_schema_list(self, capsys):
        from pyfds.cli.main import main
        rc = main(["schema"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Mesh" in captured.out

    def test_schema_entity(self, capsys):
        from pyfds.cli.main import main
        rc = main(["schema", "Mesh"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "MESH" in captured.out or "Mesh" in captured.out

    def test_schema_json(self, capsys):
        import json
        from pyfds.cli.main import main
        rc = main(["schema", "--json", "Surface"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "properties" in data

    def test_schema_unknown_entity(self):
        from pyfds.cli.main import main
        rc = main(["schema", "GhostEntity"])
        assert rc == 1

class TestExports:
    def test_selection_exports(self):
        from pyfds import SelectionManager, SelectionMode, SelectionSnapshot
        assert SelectionManager is not None
        assert SelectionMode is not None

    def test_viewport_exports(self):
        from pyfds import (
            ViewportCamera, ViewportState, ViewportController,
            TransformMode, CameraPreset, ProjectionMode, VisibilityFlags, SnapSettings,
        )
        assert ViewportController is not None

    def test_schema_exports(self):
        from pyfds import (
            PropertyDescriptor, FieldType, EntitySchema,
            SchemaRegistry, get_schema_registry,
        )
        assert get_schema_registry() is not None

    def test_factory_export(self):
        from pyfds import EntityFactory
        assert EntityFactory is not None

    def test_new_command_exports(self):
        from pyfds import (
            GroupCommand, DuplicateEntityCommand,
            SetHrrCommand, ScaleCommand,
        )
        assert GroupCommand is not None
