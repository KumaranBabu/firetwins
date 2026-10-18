# PyInstaller spec for the PyFDS desktop application (Windows, one folder).
# Build:  python packaging/build_windows.py        (output: dist/PyFDS/PyFDS.exe)
# FDS and Smokeview are not packed: put the fds_smv folder next to PyFDS.exe, or set the FDS path in Preferences.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
hidden = collect_submodules("pyfds") + collect_submodules("pyvistaqt")
datas = collect_data_files("pyvista") + collect_data_files("imageio_ffmpeg")
binaries = []
try:
    import imageio_ffmpeg
    binaries.append((imageio_ffmpeg.get_ffmpeg_exe(), "imageio_ffmpeg/binaries"))
except Exception:
    pass

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "IPython", "notebook", "PyQt5", "PyQt6"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PyFDS", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="PyFDS")
