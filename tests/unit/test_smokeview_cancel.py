"""SmokeviewRunner: cancel a running render, bundled-binary fallback."""
import sys
import threading

from pyfds.smokeview import runner as runner_mod
from pyfds.smokeview.runner import CANCELLED, SmokeviewRunner


def test_cancel_kills_the_process():
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    rc, _ = SmokeviewRunner._run_cancellable(
        [sys.executable, "-c", "import time; time.sleep(60)"], None, 60, cancel)
    assert rc == CANCELLED


def test_run_returns_exit_code_and_stderr():
    rc, err = SmokeviewRunner._run_cancellable(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"], None, 30, None)
    assert rc == 3 and err == "boom"


def test_default_binary_falls_back_to_bundled(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    resolved = SmokeviewRunner._resolve_binary("smokeview")
    assert resolved.endswith("smokeview.exe") or resolved == "smokeview"


def test_explicit_binary_is_kept(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert SmokeviewRunner._resolve_binary("C:/x/smv.exe") == "C:/x/smv.exe"
    assert runner_mod.CANCELLED < 0


def test_render_loads_the_settings_first_and_moves_images_out(tmp_path, monkeypatch):
    """The builder's settings (picture size, labels) are written beside the temporary script and loaded before
    anything else; images Smokeview writes next to the .smv are moved to the output folder - also onto another
    drive, where os.replace fails (WinError 17) - and the temporary files are removed."""
    case, out = tmp_path / "case", tmp_path / "out"
    case.mkdir()
    (case / "c.smv").write_text("")
    seen = {}

    def fake_run(cmd, cwd, timeout, cancel):
        script = cmd[cmd.index("-script") + 1]
        text = open(script).read()
        seen["script"] = text
        seen["ini"] = open(text.splitlines()[1].strip()).read()
        (case / "pic.png").write_bytes(b"png")
        return 0, ""

    def no_cross_drive(*a, **k):
        raise OSError(17, "The system cannot move the file to a different disk drive")

    monkeypatch.setattr(SmokeviewRunner, "_run_cancellable", staticmethod(fake_run))
    monkeypatch.setattr(runner_mod.os, "replace", no_cross_drive)
    rc = SmokeviewRunner(smv_binary="smv").render(str(case / "c.smv"), script_content="RENDERONCE\n pic\n",
                                                  settings_ini="WINDOWWIDTH\n 1280\n", output_dir=str(out))
    assert rc == 0
    assert seen["script"].splitlines()[0] == "LOADINIFILE" and seen["script"].rstrip().endswith("EXIT")
    assert seen["ini"] == "WINDOWWIDTH\n 1280\n"
    assert (out / "pic.png").exists() and not (case / "pic.png").exists()
    assert sorted(p.name for p in out.iterdir()) == ["pic.png"]          # temporary .ssf and .ini removed
