"""Managers added after the original facade (units, views, history of selection, find, measure, hygiene,
preferences, examples, solvers, transforms). Kept out of ``facade.py`` so that module stays small."""
from __future__ import annotations

from typing import Any


def install_extra_managers(api: Any) -> None:
    """Attach the extra managers to *api*; needs ``api.selection``, ``api.viewport`` and ``api.project``."""
    from .units import UnitsManager
    from .views import ViewsManager
    from .ui_history import UiHistory
    from .find import FindManager
    from .measure import MeasureManager
    from .hygiene import HygieneManager
    from .preferences import PreferencesManager
    from .examples import ExamplesManager
    from .solvers import SolverManager
    from .transform_ops import TransformManager
    from .sim_params import SimParamsManager
    from .updates import UpdatesManager
    from .dependencies import DependencyManager
    from .renaming import RenameManager

    api.units = UnitsManager(api)
    api.sim = SimParamsManager(api)
    api.updates = UpdatesManager(api)
    api.views = ViewsManager(api)
    api.ui_history = UiHistory(api)
    api.find = FindManager(api)
    api.dependencies = DependencyManager(api)
    api.rename = RenameManager(api)
    api.measure = MeasureManager(api)
    api.hygiene = HygieneManager(api)
    api.preferences = PreferencesManager(api)
    api.examples = ExamplesManager(api)
    api.solvers = SolverManager(api)
    api.transform = TransformManager(api)
