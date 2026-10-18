#!/usr/bin/env python3
"""PyFDS Results entry point (the Smokeview side).

Run from the repo root::

    python results_main.py [case.smv | view.pyfdsv]
"""
from pyfds.gui.results.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
