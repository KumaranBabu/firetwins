"""``python -m pyfds.gui.results [file.smv|file.pyfdsv]`` opens the window; with ``-screenshot`` / ``-movie`` it runs
the scripted command line instead (no window)."""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-screenshot", "-movie") for a in argv):
        from .cli import main as cli_main
        return cli_main(argv)
    from PySide6.QtWidgets import QApplication
    from pyfds.api.facade import FdsApi
    from .window import ResultsWindow
    app = QApplication.instance() or QApplication(sys.argv[:1])
    win = ResultsWindow(FdsApi())
    win.show()
    if argv:
        if argv[0].endswith(".pyfdsv"):
            win.viewer.open_visualization(argv[0])
            win.sync(True)
        else:
            win.open_results(argv[0])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
