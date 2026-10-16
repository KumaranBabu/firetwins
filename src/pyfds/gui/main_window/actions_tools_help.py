"""Tools and Help menu actions: diagnostics, plugin manager, unit converter, calculator, manuals."""
from __future__ import annotations

import ast
import operator
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from pyfds.gui.report_dialog import TextReportDialog


class ActionsToolsHelpMixin:
    def _on_tools_validation(self) -> None:
        # Runs plugin-registered rules too, unlike Model > Validate Project
        # (api.validation.validate()) — a superset check, not a duplicate.
        report = self.api.validation.validate_with_plugins()
        TextReportDialog("Validation (with plugin rules)", str(report), self).exec()

    def _on_find_errors(self) -> None:
        report = self.api.validation.validate()
        errors = report.errors
        if not errors:
            QMessageBox.information(self, "No errors", "Validation found no ERROR-severity issues.")
            return
        text = "\n".join(str(e) for e in errors)
        TextReportDialog("Find Errors", text, self).exec()

    def _on_mesh_diagnostics(self) -> None:
        results = self.api.meshes.check_poisson()
        if not results:
            QMessageBox.information(self, "No meshes", "No mesh regions in this project.")
            return
        lines = [
            f"{name}: {'OK — Poisson-compliant' if ok else 'WARNING — not Poisson-compliant'}"
            for name, ok in results.items()
        ]
        TextReportDialog("Mesh Diagnostics", "\n".join(lines), self).exec()

    def _on_mesh_checker(self) -> None:
        report = self.api.validation.validate()
        mesh_results = [r for r in report.results if "Mesh" in r.rule]
        if not mesh_results:
            QMessageBox.information(self, "No issues", "No mesh-related issues found (overlap, Poisson compliance).")
            return
        text = "\n".join(str(r) for r in mesh_results)
        TextReportDialog("Mesh Checker", text, self).exec()

    def _on_plugin_manager(self) -> None:
        plugins = self.api.plugins.all_plugins()
        lines = [str(p) for p in plugins] if plugins else ["No plugins currently loaded."]
        TextReportDialog("Plugin Manager", "\n".join(lines), self).exec()
        if QMessageBox.question(
            self, "Load More Plugins", "Load additional plugins from a directory?"
        ) != QMessageBox.Yes:
            return
        load_dir = QFileDialog.getExistingDirectory(self, "Plugin Directory")
        if not load_dir:
            return
        try:
            count = self.api.plugins.load_directory(load_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Could not load plugins", str(exc))
        else:
            QMessageBox.information(self, "Plugins Loaded", f"Loaded {count} plugin(s) from:\n{load_dir}")

    # Category -> {unit: factor to the category's base (SI) unit}. Temperature
    # is handled separately since C/F/K aren't related by a simple factor.
    _UNIT_CATEGORIES = {
        "Length": {"m": 1.0, "ft": 0.3048, "in": 0.0254, "mm": 0.001, "cm": 0.01},
        "Mass": {"kg": 1.0, "lb": 0.45359237, "g": 0.001},
        "HRR / Power": {"kW": 1.0, "MW": 1000.0, "BTU/s": 1.055056, "BTU/hr": 0.00029307107},
        "Velocity": {"m/s": 1.0, "ft/s": 0.3048, "ft/min": 0.00508, "mph": 0.44704},
        "Pressure": {"Pa": 1.0, "kPa": 1000.0, "bar": 1.0e5, "atm": 101325.0, "psi": 6894.757},
    }

    @staticmethod
    def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
        celsius = {"C": value, "F": (value - 32.0) * 5.0 / 9.0, "K": value - 273.15}[from_unit]
        return {"C": celsius, "F": celsius * 9.0 / 5.0 + 32.0, "K": celsius + 273.15}[to_unit]

    def _on_units_conversion(self) -> None:
        categories = list(self._UNIT_CATEGORIES.keys()) + ["Temperature"]
        category, ok = QInputDialog.getItem(self, "Units Conversion", "Category:", categories, 0, False)
        if not ok:
            return
        units = ["C", "F", "K"] if category == "Temperature" else list(self._UNIT_CATEGORIES[category].keys())
        from_unit, ok = QInputDialog.getItem(self, "Units Conversion", "From:", units, 0, False)
        if not ok:
            return
        to_unit, ok = QInputDialog.getItem(self, "Units Conversion", "To:", units, min(1, len(units) - 1), False)
        if not ok:
            return
        value, ok = QInputDialog.getDouble(self, "Units Conversion", f"Value ({from_unit}):", 0.0, -1.0e12, 1.0e12, 4)
        if not ok:
            return
        if category == "Temperature":
            result = self._convert_temperature(value, from_unit, to_unit)
        else:
            factors = self._UNIT_CATEGORIES[category]
            result = value * factors[from_unit] / factors[to_unit]
        QMessageBox.information(self, "Units Conversion", f"{value:g} {from_unit} = {result:.6g} {to_unit}")

    _CALC_OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg, ast.UAdd: operator.pos,
    }

    @classmethod
    def _safe_eval(cls, expr: str) -> float:
        """Numbers and + - * / ** % () only — no names, no calls, so this
        can never execute arbitrary code (unlike a raw eval())."""
        def _walk(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in cls._CALC_OPS:
                return cls._CALC_OPS[type(node.op)](_walk(node.left), _walk(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in cls._CALC_OPS:
                return cls._CALC_OPS[type(node.op)](_walk(node.operand))
            raise ValueError("only numbers and + - * / ** % ( ) are allowed")
        return _walk(ast.parse(expr, mode="eval").body)

    def _on_calculator(self) -> None:
        expr, ok = QInputDialog.getText(self, "Calculator", "Expression (+ - * / ** % parentheses):")
        if not ok or not expr:
            return
        try:
            result = self._safe_eval(expr)
        except Exception as exc:
            QMessageBox.warning(self, "Calculator", f"Could not evaluate {expr!r}: {exc}")
            return
        QMessageBox.information(self, "Calculator", f"{expr} = {result:g}")

    def _on_fds_preview(self) -> None:
        try:
            text = self.api.fds_text()
        except Exception as exc:
            QMessageBox.critical(self, "Could not generate preview", str(exc))
            return
        TextReportDialog("FDS Preview (EXPERIMENTAL)", text, self).exec()

    def _on_open_doc(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.information(self, "Not found", f"Expected this file but it's missing:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About PyFDS",
            "PyFDS\n\n"
            "A Python-native FDS/Smokeview modeling backend and desktop GUI — "
            "a PyroSim-workflow-inspired open alternative built on NIST FDS.",
        )
