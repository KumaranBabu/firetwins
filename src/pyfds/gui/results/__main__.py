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
    from .launcher import ResultsServer, send_open
    from .window import ResultsWindow
    app = QApplication.instance() or QApplication(sys.argv[:1])
    if argv and not argv[0].startswith("-") and send_open(argv[0]):
        return 0                                  # a viewer is already open: it takes the file, this one is not needed
    win = ResultsWindow(FdsApi())
    win.results_server = ResultsServer(win)       # the model editor and a second double-click reach this window through it
    app.aboutToQuit.connect(win.results_server.close)
    win.showMaximized()                           # the 3D view should start as large as the screen allows
    if argv:
        if argv[0].endswith(".pyfdsv"):
            win.viewer.open_visualization(argv[0])
            win.sync(True)
        else:
            win.open_results(argv[0])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
