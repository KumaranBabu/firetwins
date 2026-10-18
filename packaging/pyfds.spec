# PyInstaller spec for the PyFDS desktop applications (Windows, one folder): PyFDS.exe (the FDS model editor and run launcher)
# and PyFDSResults.exe (the Smokeview-style results viewer). They share one set of libraries.
# Build:  python packaging/build_windows.py        (output: dist/PyFDS/PyFDS.exe and PyFDSResults.exe)
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

def analysis(script):
    return Analysis(
        [str(ROOT / script)],
        pathex=[str(ROOT / "src")],
        binaries=binaries,
        datas=datas,
        hiddenimports=hidden,
        excludes=["tkinter", "pytest", "IPython", "notebook", "PyQt5", "PyQt6"],
    )


editor, viewer = analysis("main.py"), analysis("results_main.py")
MERGE((editor, "main", "PyFDS"), (viewer, "results_main", "PyFDSResults"))      # libraries both programs use are stored once
exe_editor = EXE(PYZ(editor.pure), editor.scripts, [], exclude_binaries=True, name="PyFDS", console=False)
exe_viewer = EXE(PYZ(viewer.pure), viewer.scripts, [], exclude_binaries=True, name="PyFDSResults", console=False)
coll = COLLECT(exe_editor, editor.binaries, editor.datas, exe_viewer, viewer.binaries, viewer.datas, name="PyFDS")
