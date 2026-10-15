"""Shell bars (plan step F1): the Model Settings toolbar (units, scenario, run) and the floor selector above the
navigation tree. Everything here only calls ``api``; the widgets mirror the model's state and are re-synced on
every refresh event."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel, QMessageBox, QVBoxLayout, QWidget

BASE_MODEL = "Base model"
ALL_FLOORS = "All floors"
_UNITS = [("SI", "SI"), ("English", "EN")]


# PyroSim's nine menus plus Tools, in order. Draw, HVAC, Scenarios and Floors become submenus of Model, Window one of View,
# and Run is called Analysis (decision D5 of the plan).
_MENU_ORDER = ["File", "Edit", "Model", "Devices", "Output", "Analysis", "Results", "View", "Tools", "Help"]
_FOLD_INTO = {"Model": ["Draw", "HVAC", "Scenarios", "Floors"], "View": ["Window"]}


class ShellBarsMixin:
    def _restructure_menu_bar(self) -> None:
        """Arrange the menu bar like PyroSim's. Runs after every menu has been built and extended."""
        bar = self.menuBar()
        menus = {a.text().replace("&", ""): a.menu() for a in bar.actions() if a.menu() is not None}
        if "Run" in menus:
            menus["Run"].setTitle("&Analysis")
            menus["Analysis"] = menus.pop("Run")
        for parent, children in _FOLD_INTO.items():
            if parent not in menus:
                continue
            for name in children:
                if name in menus:
                    menus[parent].addMenu(menus.pop(name))
        ordered = [menus.pop(n) for n in _MENU_ORDER if n in menus]
        bar.clear()
        for menu in ordered + list(menus.values()):
            bar.addMenu(menu)

    def _build_explorer_container(self) -> QWidget:
        """The navigation tree with the floor selector above it."""
        box = QWidget(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.floor_combo = QComboBox(box)
        self.floor_combo.setToolTip("Show only the objects of one floor")
        self.floor_combo.activated.connect(self._on_floor_chosen)
        layout.addWidget(self.floor_combo)
        layout.addWidget(self.explorer)
        return box

    def _build_shell_bars(self) -> None:
        bar = self.addToolBar("Model Settings")
        bar.setObjectName("ModelSettingsToolBar")
        bar.setMovable(False)
        bar.addWidget(QLabel(" Units "))
        self.units_combo = QComboBox(bar)
        for label, code in _UNITS:
            self.units_combo.addItem(label, code)
        self.units_combo.setToolTip("Units shown and typed in dialogs (the model is always stored in SI)")
        self.units_combo.activated.connect(self._on_units_chosen)
        bar.addWidget(self.units_combo)
        bar.addSeparator()
        bar.addWidget(QLabel(" Scenario "))
        self.scenario_combo = QComboBox(bar)
        self.scenario_combo.setToolTip("Scenario applied to the model")
        self.scenario_combo.setMinimumContentsLength(12)
        self.scenario_combo.activated.connect(self._on_scenario_chosen)
        bar.addWidget(self.scenario_combo)
        bar.addAction(self._run_action)
        self._sync_shell_bars()

    def _sync_shell_bars(self) -> None:
        """Make the combos show the model's current state, without firing their handlers."""
        if not hasattr(self, "units_combo"):
            return
        api = self.api
        self.units_combo.blockSignals(True)
        self.units_combo.setCurrentIndex(max(0, self.units_combo.findData(api.units.system)))
        self.units_combo.blockSignals(False)

        self.scenario_combo.blockSignals(True)
        self.scenario_combo.clear()
        self.scenario_combo.addItem(BASE_MODEL, None)
        for sc in api.scenarios.all():
            self.scenario_combo.addItem(sc.name, sc.name)
        active = api.scenarios.active
        self.scenario_combo.setCurrentIndex(max(0, self.scenario_combo.findData(active)) if active else 0)
        self.scenario_combo.blockSignals(False)

        current = self.floor_combo.currentData()
        self.floor_combo.blockSignals(True)
        self.floor_combo.clear()
        self.floor_combo.addItem(ALL_FLOORS, None)
        for fl in api.floors.all_floors():
            self.floor_combo.addItem(fl.name, fl.name)
        idx = self.floor_combo.findData(current) if current else 0
        self.floor_combo.setCurrentIndex(max(0, idx))
        self.floor_combo.blockSignals(False)

    # -- handlers ---------------------------------------------------------------------------------
    def _on_units_chosen(self, index: int) -> None:
        system = self.units_combo.itemData(index)
        self.api.units.set_system(system)
        self.statusBar().showMessage(f"Units: {'English' if system == 'EN' else 'SI'}", 4000)

    def _on_scenario_chosen(self, index: int) -> None:
        name = self.scenario_combo.itemData(index)
        try:
            if name is None:
                self.api.scenarios.reset()
            else:
                self.api.scenarios.apply(name)
        except Exception as exc:
            QMessageBox.critical(self, "Could not switch scenario", str(exc))
        finally:
            self._sync_shell_bars()

    def _on_floor_chosen(self, index: int) -> None:
        name = self.floor_combo.itemData(index)
        if name is None:
            self.api.view.show_all()
            return
        members = self.api.floors.entities_on_floor(name)
        if members:
            self.api.view.isolate(members)
        else:
            self.statusBar().showMessage(f"Floor {name} has no objects", 4000)
