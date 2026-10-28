"""Shared helpers for the client-demo walkthrough scripts.

The scripts open the real PyFDS windows on the desktop (native Qt platform, the real GPU), fill the real dialogs the
way a user would, and save what the screen shows with ``QWidget.grab()``: every picture in the manual is the actual
application. Each step's outcome is appended to ``validation_log.json`` next to the screenshots, so the validation
report is built from what happened, not from what was expected.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.pop("QT_QPA_PLATFORM", None)                    # the real screen, never offscreen

from PySide6.QtCore import QTimer                          # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QMessageBox, QTabWidget, QWidget   # noqa: E402


class Demo:
    def __init__(self, name: str) -> None:
        self.name = name
        self.shots_dir = ROOT / "documentation" / "screenshots" / name
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        for old in self.shots_dir.glob("*.png"):
            old.unlink()
        self.log_path = self.shots_dir / "validation_log.json"
        self.log: List[dict] = []
        self.n = 0
        self.app = QApplication.instance() or QApplication([])
        from pyfds.gui.theme import apply_theme, saved_theme
        apply_theme(saved_theme(), self.app, remember=False)
        sys.excepthook = self._die
        self._watch = QTimer()
        self._watch.timeout.connect(self._message_boxes)
        self._watch.start(1200)

    # -- recording ------------------------------------------------------------------------------------------------------
    def step(self, title: str, outcome: str = "ok", detail: Any = None) -> None:
        self.log.append({"step": title, "outcome": outcome, "detail": detail, "time": time.strftime("%H:%M:%S")})
        self.log_path.write_text(json.dumps(self.log, indent=1, default=str), encoding="utf-8")
        print(f"[{outcome}] {title}" + (f"  {detail}" if detail not in (None, "") else ""))
        sys.stdout.flush()

    def _die(self, kind, exc, tb) -> None:
        traceback.print_exception(kind, exc, tb)
        self.step("unhandled error", "failed", f"{kind.__name__}: {exc}")
        sys.stdout.flush()
        os._exit(1)

    def pump(self, seconds: float = 0.3) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)

    def shot(self, widget, name: str, caption: str, settle: float = 0.5) -> str:
        """Save the widget as it is on screen; the caption goes to the log for the manual."""
        self.pump(settle)
        self.n += 1
        file = f"{self.n:02d}_{name}.png"
        widget.grab().save(str(self.shots_dir / file))
        size = [QWidget.width(widget), QWidget.height(widget)]      # some dialogs have a field called 'width'
        self.log.append({"screenshot": file, "caption": caption, "size": size})
        self.log_path.write_text(json.dumps(self.log, indent=1, default=str), encoding="utf-8")
        print("   screenshot", file)
        return file

    def _message_boxes(self) -> None:
        """A message box that appears while the script runs is photographed, logged and answered."""
        m = self.app.activeModalWidget()
        if isinstance(m, QMessageBox) and not getattr(self, "_in_drive", False):
            self.shot(m, "message", f"Message: {m.windowTitle()}", settle=0.2)
            self.step(f"message box: {m.windowTitle()}", "info", m.text()[:300])
            m.accept()

    # -- driving dialogs ---------------------------------------------------------------------------------------------------
    def drive(self, open_fn: Callable[[], Any], name: Optional[str], caption: str, fill: Optional[Callable[[Any], None]] = None,
              accept: bool = True, extra_shots: Optional[Callable[[Any], None]] = None) -> Any:
        """``open_fn`` opens a modal dialog. Fill it, photograph the completed dialog, then press OK (or Cancel)."""
        seen = {}

        def handler() -> None:
            dlg = self.app.activeModalWidget()
            if dlg is None or isinstance(dlg, QMessageBox) and not seen:
                QTimer.singleShot(150, handler)
                return
            self._in_drive = True
            try:
                seen["dlg"] = dlg
                if fill:
                    fill(dlg)
                if name:                                  # None: the same dialog again, filled without a picture
                    self.shot(dlg, name, caption)
                if extra_shots:
                    extra_shots(dlg)
            finally:
                self._in_drive = False
            dlg.accept() if accept else dlg.reject()

        QTimer.singleShot(350, handler)
        result = open_fn()
        self.pump(0.4)
        return seen.get("dlg") if result is None else result

    def tab_shots(self, dlg, tabs: QTabWidget, wanted: List[str], prefix: str, caption: str) -> None:
        """Photograph the named tabs of a dialog (the first tab is in the main shot)."""
        for i in range(tabs.count()):
            label = tabs.tabText(i).replace("&", "")
            if label in wanted:
                tabs.setCurrentIndex(i)
                self.shot(dlg, f"{prefix}_{label.lower().replace(' ', '_')}", f"{caption}: {label} tab")
        tabs.setCurrentIndex(0)

    @staticmethod
    def set_field(dlg, name: str, value) -> None:
        w = dlg._fields[name]
        if isinstance(w, QCheckBox):
            w.setChecked(bool(value))
        elif isinstance(w, QComboBox):
            w.setCurrentText(str(value))
        else:
            w.setText(str(value))

    def fields(self, **vals):
        return lambda dlg: [self.set_field(dlg, k, v) for k, v in vals.items()]

    @staticmethod
    def menu_action(win, menu: str, text: str):
        def walk(m):
            for act in m.actions():
                yield act
                if act.menu() is not None:
                    yield from walk(act.menu())
        tops = sorted(win.menuBar().actions(), key=lambda t: t.text().replace("&", "") != menu)
        for top in tops:
            for act in walk(top.menu()):
                if act.text().replace("&", "") == text:
                    return act
        raise KeyError(f"{menu} > {text}")

    def menu_shot(self, win, title: str, name: str, caption: str) -> None:
        for top in win.menuBar().actions():
            if top.text().replace("&", "") == title:
                m = top.menu()
                m.popup(win.mapToGlobal(win.menuBar().actionGeometry(top).bottomLeft()))
                self.pump(0.4)
                self.shot(m, name, caption, settle=0.2)
                m.hide()
                return
        raise KeyError(title)


class ScreenRecorder:
    """An MP4 of the real screen while a walkthrough runs: every window and dialog as the user would see them.

    Frames come from a Qt timer, so they keep coming while modal dialogs are open. ``timelapse(seconds)`` slows the
    capture down (one frame per *seconds*) for the long wait while FDS runs; ``realtime()`` goes back."""

    def __init__(self, path: Path, fps: int = 5) -> None:
        import imageio_ffmpeg
        from PIL import ImageGrab
        self._grab = ImageGrab.grab
        first = self._grab()
        self.size = (first.width // 8 * 8, first.height // 8 * 8)
        self.path, self.fps, self.frames = Path(path), fps, 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._gen = imageio_ffmpeg.write_frames(str(self.path), self.size, fps=fps, codec="libx264",
                                                pix_fmt_out="yuv420p", quality=7, macro_block_size=8)
        self._gen.send(None)
        self._timer = QTimer()
        self._timer.timeout.connect(self.frame)
        self.realtime()

    def frame(self) -> None:
        try:
            img = self._grab().convert("RGB").crop((0, 0) + self.size)
            self._gen.send(img.tobytes())
            self.frames += 1
        except Exception as exc:                                  # noqa: BLE001 - a lost frame must not stop the demo
            print("recorder:", exc)

    def realtime(self) -> None:
        self._timer.start(int(1000 / self.fps))

    def timelapse(self, seconds_per_frame: float) -> None:
        self._timer.start(int(1000 * seconds_per_frame))

    def close(self) -> dict:
        self._timer.stop()
        self.frame()
        self._gen.close()
        return {"video": str(self.path), "frames": self.frames, "seconds": round(self.frames / self.fps, 1)}


def shown_window() -> Any:
    """``startupinfo`` for subprocess.Popen: show the program's window even when this script was started hidden
    (a hidden parent otherwise passes SW_HIDE on to the programs it starts)."""
    import subprocess
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 1                                            # SW_SHOWNORMAL
    return si


def window_shot(pid: int, path: Path) -> bool:
    """A picture of the main window of another program (Smokeview, process *pid*); nothing else of the desktop is
    captured. False when that process has no visible window."""
    try:
        import win32gui
        import win32process
    except ImportError:
        return False
    found = []
    win32gui.EnumWindows(lambda h, _: found.append(h) if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h)
                         and win32process.GetWindowThreadProcessId(h)[1] == pid else None, None)
    if not found:
        return False
    try:
        win32gui.SetForegroundWindow(found[0])
    except Exception:                                             # noqa: BLE001 - Windows may refuse; grab anyway
        pass
    time.sleep(0.5)
    return screen_shot_of_desktop(path, win32gui.GetWindowRect(found[0]))


def screen_shot_of_desktop(path: Path, region=None) -> bool:
    """A picture of the real screen (for a program that is not a Qt window, such as Smokeview)."""
    try:
        from PIL import ImageGrab
        ImageGrab.grab(bbox=region).save(str(path))
        return True
    except Exception as exc:                                      # noqa: BLE001
        print("desktop screenshot failed:", exc)
        return False
