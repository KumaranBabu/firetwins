"""Build the Windows application folder with PyInstaller: ``python packaging/build_windows.py [work_dir]``.

Output goes to ``<work_dir>/dist/PyFDS`` with PyFDS.exe (the editor) and PyFDSResults.exe (the results viewer) side by side (default: ``dist/`` and ``build/`` in the repository, both gitignored).
Then copy ``fds_smv/`` next to ``PyFDS.exe`` if the package should find FDS and Smokeview by itself."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    work = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE.parent
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--distpath", str(work / "dist"), "--workpath", str(work / "build"), str(HERE / "pyfds.spec")]
    print(" ".join(cmd))
    env = dict(os.environ)
    env.setdefault("PYINSTALLER_CONFIG_DIR", str(work / "build" / ".pyinstaller"))     # its cache stays out of the user profile
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
