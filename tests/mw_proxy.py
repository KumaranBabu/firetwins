"""Patch target for the main-window package.

``pyfds.gui.main_window`` is a package of small modules; a name such as ``SchemaFormDialog`` or ``QSettings`` is imported by
whichever modules use it. ``main_window_mod`` stands in for the old single module: reading a name finds it, and
``monkeypatch.setattr(main_window_mod, "SchemaFormDialog", fake)`` replaces it in every module of the package that has it.
"""
from __future__ import annotations

import importlib
import pkgutil

import pyfds.gui.main_window as _pkg


def _modules():
    yield _pkg
    for info in pkgutil.iter_modules(_pkg.__path__):
        if info.name.startswith("__"):              # __main__ would start the application
            continue
        yield importlib.import_module(f"{_pkg.__name__}.{info.name}")


class _MainWindowModules:
    def __getattr__(self, name):
        for mod in _modules():
            if hasattr(mod, name):
                return getattr(mod, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        hit = [m for m in _modules() if name in vars(m)]
        if not hit:
            raise AttributeError(f"no module of pyfds.gui.main_window has {name!r}")
        for mod in hit:
            setattr(mod, name, value)


main_window_mod = _MainWindowModules()
