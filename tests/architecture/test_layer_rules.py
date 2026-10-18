"""Architecture guard-rails (plan step G1).

Enforces the layering from ``docs/PYFDS.docx`` §4
with a **ratchet**: ``KNOWN_VIOLATIONS`` / ``OVERSIZE_BASELINE`` list today's debt.
New violations fail the test; fixing one without removing its entry also fails, so
the lists only ever shrink.

Rules
-----
* Import direction between top-level packages follows ``ALLOWED`` (no upward imports).
* No import cycles between top-level packages.
* No Qt (``PySide6``) outside ``pyfds.gui``; PyVista only in ``gui`` (+ baseline).
* Modules stay under ``MAX_LINES`` lines (+ baseline of existing monoliths).
"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "pyfds"
REPO = Path(__file__).resolve().parents[2]
MAX_LINES = 400           # every module stays small (docs/PYFDS.docx §3); split before adding more

_LOW = {"core", "utils"}
ALLOWED: dict[str, set[str]] = {
    "core":        set(),
    "utils":       {"core"},
    "domain":      {"core", "utils"},
    "io":          {"core", "utils", "domain"},
    "validation":  {"core", "utils", "domain"},
    "engineering": {"core", "utils", "domain"},
    "tenability":  {"core", "utils", "domain"},
    "results":     {"core", "utils"},
    "smokeview":   {"core", "utils", "results"},
    "meshing":     {"core", "utils", "domain"},
    "execution":   {"core", "utils", "domain", "io", "results"},
    "plugins":     {"core", "utils", "domain", "validation"},
    "automation":  {"core", "utils", "domain", "io", "execution", "results", "smokeview", "validation"},
    "api":         {"core", "utils", "domain", "io", "validation", "engineering", "tenability",
                    "results", "smokeview", "meshing", "execution", "plugins", "automation"},
    # adapters: api (+ shared kernel) only
    "agent":       {"core", "utils", "api"},
    "cli":         {"core", "utils", "api"},
    "gui":         {"core", "utils", "api", "agent"},
}

# (importing module, imported package): known debt, removed by G5 (route adapters via ``api``).
KNOWN_VIOLATIONS: set[tuple[str, str]] = set()   # G5 done: adapters reach everything through ``api``

OVERSIZE_BASELINE = {   # path relative to src/pyfds -> allowed max lines (never raise)
            
    
}
PYVISTA_BASELINE = {"domain/geometry_tools_common.py"}   # lazy import for CSG booleans (move to infrastructure)


def _modules():
    for f in sorted(SRC.rglob("*.py")):
        rel = f.relative_to(SRC)
        if len(rel.parts) == 1:          # pyfds/__init__.py: public re-export surface
            continue
        yield f, rel


def _type_checking_nodes(tree):
    skip = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.If) and "TYPE_CHECKING" in ast.dump(n.test):
            for c in ast.walk(n):
                skip.add(id(c))
    return skip


def _imports(f: Path, rel: Path):
    """Yield (target top-level pyfds package, lineno, dotted name) for runtime imports."""
    tree = ast.parse(f.read_text(encoding="utf-8"))
    skip = _type_checking_nodes(tree)
    for n in ast.walk(tree):
        if id(n) in skip:
            continue
        if isinstance(n, ast.ImportFrom):
            if n.level == 0:
                if n.module and n.module.split(".")[0] == "pyfds" and "." in n.module:
                    yield n.module.split(".")[1], n.lineno, n.module
            else:
                base = list(rel.parts[:-1])
                base = base[: len(base) - (n.level - 1)]
                full = base + (n.module.split(".") if n.module else [])
                if full:
                    yield full[0], n.lineno, ".".join(full)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("pyfds."):
                    yield a.name.split(".")[1], n.lineno, a.name


def _edges():
    """(importer package, imported package) -> ["module:line", ...]"""
    edges: dict[tuple[str, str], list[str]] = defaultdict(list)
    for f, rel in _modules():
        pkg = rel.parts[0]
        for target, line, _ in _imports(f, rel):
            if target != pkg:
                edges[(pkg, target)].append(f"{rel.as_posix()}:{line}")
    return edges


def _violations():
    """(module, imported package) -> lines, for imports the layer map forbids."""
    out: dict[tuple[str, str], list[int]] = defaultdict(list)
    for (pkg, target), where in _edges().items():
        if target in ALLOWED.get(pkg, set()):
            continue
        for w in where:
            mod, line = w.rsplit(":", 1)
            out[(mod, target)].append(int(line))
    return out


def test_every_package_has_a_rule():
    pkgs = {rel.parts[0] for _, rel in _modules()}
    assert pkgs <= set(ALLOWED), f"add layer rules for: {sorted(pkgs - set(ALLOWED))}"


def test_import_direction_follows_layers():
    bad = {k: v for k, v in _violations().items() if k not in KNOWN_VIOLATIONS}
    msg = "\n".join(f"  {m} -> {t} (lines {v[:3]})" for (m, t), v in sorted(bad.items()))
    assert not bad, f"upward/forbidden imports (see plan §4.1):\n{msg}"


def test_known_violations_not_stale():
    stale = KNOWN_VIOLATIONS - set(_violations())
    assert not stale, f"fixed; remove from KNOWN_VIOLATIONS: {sorted(stale)}"


def test_no_package_cycles():
    graph: dict[str, set[str]] = defaultdict(set)
    for (a, b) in _edges():
        graph[a].add(b)
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(n):
        state[n] = 1
        stack.append(n)
        for m in sorted(graph.get(n, ())):
            if state.get(m) == 1:
                raise AssertionError("package cycle: " + " -> ".join(stack[stack.index(m):] + [m]))
            if m not in state:
                visit(m)
        stack.pop()
        state[n] = 2

    for n in sorted(graph):
        if n not in state:
            visit(n)


def test_qt_only_in_gui():
    offenders = []
    for f, rel in _modules():
        if rel.parts[0] == "gui":
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            names = ([n.module or ""] if isinstance(n, ast.ImportFrom) and n.level == 0
                     else [a.name for a in n.names] if isinstance(n, ast.Import) else [])
            for name in names:
                top = name.split(".")[0]
                if top in {"PySide6", "PyQt5", "PyQt6", "pyvistaqt"} or (
                        top == "pyvista" and rel.as_posix() not in PYVISTA_BASELINE):
                    offenders.append(f"{rel.as_posix()}:{n.lineno} imports {name}")
    assert not offenders, "GUI toolkit outside pyfds.gui:\n  " + "\n  ".join(offenders)


def test_file_size_budget():
    over = []
    for f, rel in _modules():
        n = len(f.read_text(encoding="utf-8").splitlines())
        limit = OVERSIZE_BASELINE.get(rel.as_posix(), MAX_LINES)
        if n > limit:
            over.append(f"{rel.as_posix()}: {n} lines > {limit}")
    assert not over, "split the module (plan §4 conventions):\n  " + "\n  ".join(over)


def test_oversize_baseline_not_stale():
    stale = []
    for rel, limit in OVERSIZE_BASELINE.items():
        n = len((SRC / rel).read_text(encoding="utf-8").splitlines())
        if n <= MAX_LINES:
            stale.append(rel)
    assert not stale, f"now under {MAX_LINES} lines; drop from OVERSIZE_BASELINE: {stale}"


def test_tests_examples_and_tools_stay_small_too():
    """The same limit applies to the test files, the example scripts and the tools."""
    over = []
    roots = [REPO / "tests", REPO / "examples", REPO / "tools"]
    files = [f for r in roots if r.exists() for f in sorted(r.rglob("*.py"))] + [REPO / "main.py"]
    for f in files:
        if "__pycache__" in f.parts or not f.exists():
            continue
        n = len(f.read_text(encoding="utf-8").splitlines())
        if n > MAX_LINES:
            over.append(f"{f.relative_to(REPO).as_posix()}: {n} lines > {MAX_LINES}")
    assert not over, f"split these files: {over}"
