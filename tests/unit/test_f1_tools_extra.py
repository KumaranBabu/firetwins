"""F1: Script Console, Tutorials and Check for Updates (offscreen; git is faked, nothing touches the network)."""
import os
import subprocess
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pyfds.api import FdsApi
from pyfds.core.updates import UpdateStatus, check_for_updates, repo_root

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from pyfds.gui.script_console import ScriptConsoleDialog, ScriptSession  # noqa: E402
from pyfds.gui.tutorials_dialog import TutorialsDialog, find_tutorials  # noqa: E402
from pyfds.gui.update_dialog import UpdateDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


# -- updates -------------------------------------------------------------------------------------------------------------------
class FakeGit:
    """Answers the few git commands the checker uses."""

    def __init__(self, local="a" * 40, remote="b" * 40, have_remote=True, ancestor=False, behind=3, ahead=0,
                 ls_rc=0, ls_err="", raise_exc=None):
        self.__dict__.update(locals())
        self.calls = []

    def __call__(self, args, cwd, timeout):
        self.calls.append(list(args))
        if self.raise_exc:
            raise self.raise_exc
        def done(out="", rc=0, err=""):
            return subprocess.CompletedProcess(args, rc, out, err)
        a = list(args)
        if a[:2] == ["git", "rev-parse"]:
            return done(self.local + "\n")
        if a[:2] == ["git", "ls-remote"]:
            return done(f"{self.remote}\trefs/heads/main\n" if self.ls_rc == 0 else "", self.ls_rc, self.ls_err)
        if a[:2] == ["git", "cat-file"]:
            return done(rc=0 if self.have_remote else 1)
        if a[:2] == ["git", "merge-base"]:
            return done(rc=0 if self.ancestor else 1)
        if a[:2] == ["git", "rev-list"]:
            return done(f"{self.ahead if a[-1].startswith(self.remote) else self.behind}\n")
        raise AssertionError(a)


def test_up_to_date():
    s = check_for_updates(Path("."), runner=FakeGit(local="c" * 40, remote="c" * 40))
    assert s.state == "up_to_date" and s.behind == 0


def test_remote_commit_not_known_locally_means_an_update_without_a_count():
    s = check_for_updates(Path("."), runner=FakeGit(have_remote=False))
    assert s.state == "behind" and s.behind is None and "git pull" in s.message


def test_remote_is_an_ancestor_means_this_copy_is_ahead():
    git = FakeGit(ancestor=True, ahead=2)
    s = check_for_updates(Path("."), runner=git)
    assert s.state == "ahead" and s.ahead == 2 and "not pushed" in s.message


def test_known_newer_commits_are_counted_and_diverged_is_told_apart():
    s = check_for_updates(Path("."), runner=FakeGit(behind=5, ahead=0))
    assert s.state == "behind" and s.behind == 5 and "5 newer" in s.message
    d = check_for_updates(Path("."), runner=FakeGit(behind=4, ahead=1))
    assert d.state == "diverged" and d.behind == 4 and d.ahead == 1 and "--rebase" in d.message


def test_the_check_is_read_only():
    git = FakeGit(have_remote=False)
    check_for_updates(Path("."), runner=git)
    verbs = {c[1] for c in git.calls}
    assert verbs <= {"rev-parse", "ls-remote", "cat-file", "merge-base", "rev-list"}      # no fetch, pull, checkout ...


@pytest.mark.parametrize("git,needle", [
    (FakeGit(ls_rc=128, ls_err="fatal: unable to access: could not resolve host"), "Could not reach the remote"),
    (FakeGit(raise_exc=FileNotFoundError()), "git is not installed"),
    (FakeGit(raise_exc=subprocess.TimeoutExpired("git", 1)), "did not answer in time"),
    (FakeGit(local=""), "Could not read the current version"),
])
def test_problems_become_unknown_not_exceptions(git, needle):
    s = check_for_updates(Path("."), runner=git)
    assert s.state == "unknown" and needle in s.message


def test_a_copy_that_is_not_a_checkout_says_so(tmp_path, monkeypatch):
    assert repo_root(tmp_path) is None                                            # no .git here or above
    monkeypatch.setattr("pyfds.core.updates.repo_root", lambda start=None: None)
    git = FakeGit()
    s = check_for_updates(runner=git)
    assert s.state == "unknown" and "not a git checkout" in s.message and git.calls == []   # git was never run


def test_this_source_tree_is_found_as_a_checkout():
    assert repo_root() is not None and (repo_root() / ".git").exists()


def test_update_dialog_shows_the_result_and_survives_a_crashing_check(qapp):
    d = UpdateDialog(FdsApi(), None, check=lambda: UpdateStatus("behind", "2 newer commit(s) are available.", "a" * 40, "b" * 40, 2))
    assert d.wait() and d.status.state == "behind" and "2 newer" in d.label.text() and "aaaaaaaaaa" in d.detail.text()
    d.close()
    def boom():
        raise RuntimeError("kaput")
    d2 = UpdateDialog(FdsApi(), None, check=boom)
    assert d2.wait() and d2.status.state == "unknown" and "kaput" in d2.label.text()
    d2.close()


# -- tutorials ----------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def docs(tmp_path):
    (tmp_path / "pyrosim").mkdir()
    (tmp_path / "FDS").mkdir()
    for rel in ("pyrosim/2020.1 Modeling Jet Fans _ Thunderhead Support.pdf", "pyrosim/Basic Data Output _ Thunderhead Support.pdf",
                "FDS/FDS_User_Guide.pdf", "intro.pdf", "FDS/notes.txt"):
        (tmp_path / rel).write_bytes(b"%PDF-1.4")
    return tmp_path


def test_tutorial_titles_are_cleaned_and_grouped(docs):
    found = find_tutorials(docs)
    assert [(d["group"], d["title"]) for d in found] == [
        ("FDS", "FDS User Guide"), ("General", "intro"), ("pyrosim", "Basic Data Output"), ("pyrosim", "Modeling Jet Fans")]
    assert all(d["path"].endswith(".pdf") for d in found)
    assert find_tutorials(docs / "missing") == []


def test_tutorials_dialog_filters_and_opens_the_chosen_one(docs):
    opened = []
    d = TutorialsDialog(None, docs, opened.append)
    assert len(d.titles()) == 4 and "4 of 4" in d.note.text()
    d.filter.setText("jet")
    assert d.titles() == ["Modeling Jet Fans   [pyrosim]"]
    path = d.open_selected()
    assert opened == [path] and path.endswith("Modeling Jet Fans _ Thunderhead Support.pdf")
    d.filter.setText("zzz")
    assert d.titles() == [] and not d.open_button.isEnabled() and d.open_selected() is None
    d.close()


def test_tutorials_dialog_says_where_it_looked_when_there_are_none(tmp_path):
    d = TutorialsDialog(None, tmp_path / "none")
    assert "No tutorial documents" in d.note.text() and str(tmp_path / "none") in d.note.text()
    d.close()


# -- script console ----------------------------------------------------------------------------------------------------------------
@pytest.fixture
def session():
    return ScriptSession(FdsApi(), "WINDOW")


def test_expressions_show_their_value_and_statements_run(session):
    assert session.execute("1 + 2").value == "3"
    r = session.execute("x = 5\nprint('hi', x)")
    assert r.ok and r.output == "hi 5\n" and r.value is None
    assert session.execute("x * 2").value == "10" and session.execute("_").value == "10"
    assert session.execute("window").value == "'WINDOW'"
    assert session.execute("   ").output == "" and len(session.history) == 5


def test_code_can_drive_the_api_and_every_change_is_undoable(session):
    api = session.namespace["api"]
    assert session.execute("api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name='TABLE').name").value == "'TABLE'"
    assert api.obstructions.get("TABLE") is not None
    api.history.undo()
    assert api.obstructions.all() == []


def test_errors_are_reported_briefly_and_never_raise(session):
    r = session.execute("1 / 0")
    assert not r.ok and "ZeroDivisionError" in r.error
    assert "<console>" in session.execute("undefined_name").error
    bad = session.execute("def f(:")
    assert not bad.ok and "SyntaxError" in bad.error
    assert "ignored" in session.execute("raise SystemExit").error
    assert session.execute("1 + 1").value == "2"                                  # the session is still usable


def test_history_recall_moves_through_earlier_input(session):
    for line in ("a = 1", "b = 2", "c = 3"):
        session.execute(line)
    assert session.recall(3, -1) == 2 and session.recall(0, -1) == 0 and session.recall(2, +1) == 3 and session.recall(3, +1) == 3


def test_console_dialog_runs_input_and_shows_the_output(qapp):
    d = ScriptConsoleDialog(FdsApi(), None)
    d.input.setPlainText("print('hello')\n2 + 2")
    r = d.run()                                                                    # not one expression: run as statements
    assert r.ok and "hello" in d.output.toPlainText()
    d.input.setPlainText("40 + 2")
    d.run()
    text = d.output.toPlainText()
    assert ">>> 40 + 2" in text and "42" in text and d.input.toPlainText() == ""
    d.input.setPlainText("1/0")
    d.run()
    assert "ZeroDivisionError" in d.output.toPlainText()
    d.recall(-1)
    assert d.input.toPlainText() == "1/0"
    d.recall(+1)
    assert d.input.toPlainText() == ""
    d.clear_button.click()
    assert ">>>" not in d.output.toPlainText()
    d.close()


# -- the menus -------------------------------------------------------------------------------------------------------------------------
def test_menu_entries_are_real_and_open_the_dialogs(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    from pyfds.gui.main_window.placeholders import PLACEHOLDERS
    assert not [k for k in PLACEHOLDERS if any(t in k for t in ("script_console", "tutorials", "check_updates"))]
    monkeypatch.setattr(TutorialsDialog, "exec", lambda self: 0)
    monkeypatch.setattr(UpdateDialog, "exec", lambda self: 0)
    w = MainWindow(FdsApi())
    tools = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Tools")
    help_ = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Help")
    find = lambda m, label: next(a for a in m.actions() if a.text().replace("&", "") == label)
    find(tools, "Script Console...").trigger()
    first = w._script_console
    find(tools, "Script Console...").trigger()
    assert w._script_console is first and first.isVisible()                          # one console, brought forward
    find(help_, "Tutorials...").trigger()
    find(help_, "Check for Updates...").trigger()
    assert isinstance(w._tutorials_dialog, TutorialsDialog) and isinstance(w._update_dialog, UpdateDialog)
    w._update_dialog.wait()
    first.close()
    w.close()
