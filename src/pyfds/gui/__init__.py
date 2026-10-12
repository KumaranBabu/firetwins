"""PyFDS GUI layer (PySide6). Every widget is a pure view over ``FdsApi`` —
see src/pyfds/agent (ai-agentic-gui memory) for the "never bypass FdsApi" rule
that applies to both human-driven widgets and the AI chat panel."""

import os as _os
import sys as _sys

if _sys.platform == "win32":
    # Qt >= 6.10 imports the *unversioned* ICU exports (icuuc.dll). In conda
    # environments Libraryin\icuuc.dll (versioned exports) shadows the
    # Windows system copy, so QtCore fails with "DLL load failed ... procedure
    # could not be found". Loading the system copy first makes the loader
    # reuse it for Qt. Harmless when absent or when Qt does not need it.
    try:
        import ctypes as _ctypes

        _icu = _os.path.join(_os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icuuc.dll")
        if _os.path.exists(_icu):
            _ctypes.WinDLL(_icu)
    except OSError:
        pass
