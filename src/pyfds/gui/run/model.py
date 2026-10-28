"""Run setup logic for the Run FDS dialogs (plan step F6), free of Qt so it is tested directly.

A ``RunSetup`` says where and how to run (this machine, MPI on this machine, a cluster host table, or a remote
provider). ``problems`` lists what would stop it, ``assignment`` shows which meshes each process or host gets, and
``start`` hands it to ``api.solvers``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MODES = ("local", "parallel", "cluster", "cloud")
TITLES = {"local": "Run FDS", "parallel": "Run FDS Parallel", "cluster": "Run FDS Cluster", "cloud": "Run FDS Cloud"}


@dataclass
class RunSetup:
    mode: str = "local"
    output_dir: str = ""
    processes: int = 1
    hosts: List[str] = field(default_factory=list)            # "name:processes", in mesh order
    provider: str = "directory"
    provider_config: Dict[str, Any] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)     # fds_version, vcpus, memory_gb_per_vcpu ...
    install: Optional[str] = None                             # name of an FDS install (api.solvers.installs)
    open_smokeview: bool = False
    validate_first: bool = True


def default_setup(api: Any, mode: str = "local") -> RunSetup:
    if mode not in MODES:
        raise ValueError(f"unknown run mode {mode!r}")
    meshes = api.meshes.run_count()
    setup = RunSetup(mode=mode)
    if mode == "parallel":
        setup.processes = max(meshes, 1)
    elif mode == "cluster":
        setup.hosts = [f"localhost:{max(meshes, 1)}"]
    elif mode == "cloud":
        setup.options = {"vcpus": max(meshes, 1), "memory_gb_per_vcpu": 2}
    return setup


def assignment(api: Any, setup: RunSetup) -> List[Dict[str, Any]]:
    """Which meshes each process / host runs: ``[{"host", "ranks", "meshes"}, ...]``."""
    n = api.meshes.run_count()
    if setup.mode == "cluster":
        return api.solvers.cluster_plan(setup.hosts, setup.output_dir or None)["assignment"]
    if setup.mode == "parallel":                   # one row per process: process i runs mesh i
        return [{"host": f"Process {i + 1}", "ranks": [i], "meshes": [i] if i < n else []}
                for i in range(max(setup.processes, 1))]
    return api.solvers.cluster_plan(["localhost:1"])["assignment"] if n else []


def fds_available(api: Any) -> bool:
    """True when a run on this computer would find FDS: the configured executable, or a detected install."""
    from pathlib import Path
    try:
        path = api.solvers.selected().get("path")
        return bool(path and Path(path).is_file()) or bool(api.solvers.installs(probe=False))
    except Exception:
        return False


def problems(api: Any, setup: RunSetup, report: Any = None, fds_found: Optional[bool] = None) -> List[str]:
    """Reasons the run cannot start; an empty list means it can.

    *report* is a validation report already made (the dialog validates once, not on every keystroke); *fds_found*
    False adds 'FDS not found' for a run on this computer (None: not checked)."""
    out: List[str] = []
    n = api.meshes.run_count()
    if setup.mode not in MODES:
        return [f"unknown run mode {setup.mode!r}"]
    if not setup.output_dir.strip():
        out.append("choose a folder for the input and results")
    if n == 0:
        out.append("the model has no mesh")
    if setup.mode == "parallel":
        if n < 2:
            out.append("a parallel run needs at least two meshes")
        elif setup.processes != n:
            out.append(f"{setup.processes} processes for {n} meshes: FDS needs one process per mesh")
    elif setup.mode == "cluster" and n:
        out += api.solvers.cluster_plan(setup.hosts, setup.output_dir or None)["problems"]
    elif setup.mode == "cloud":
        if setup.provider not in api.solvers.cloud_providers():
            out.append(f"no remote provider named {setup.provider!r} is registered")
        elif setup.provider == "directory" and not setup.provider_config.get("root"):
            out.append("the directory provider needs a spool folder")
    if fds_found is False and setup.mode in ("local", "parallel"):
        out.append("FDS was not found on this computer: use Locate FDS... to pick fds.exe")
    if setup.validate_first and n and (report.errors if report is not None else not api.validation.can_run()):
        out.append("the model has errors; see Model Checks")
    return out


_IMBALANCE = 1.5          # the busiest process may carry this much more than the average before it is pointed out


def summary(api: Any, setup: RunSetup, report: Any = None) -> Dict[str, Any]:
    """What the run will compute, for the dialog: cells per mesh (multipliers expanded), cell sizes, the cells each
    process gets, and the validation counts. Nothing here estimates time or memory: those depend on the machine."""
    meshes = [c for m in api.project.meshes for c in api.meshes.copies_of(m)]     # multipliers expanded
    cells, sizes = [], []
    for m in meshes:
        i, j, k = m.cell_count
        cells.append(i * j * k)
        sizes += [(m.x_max - m.x_min) / i, (m.y_max - m.y_min) / j, (m.z_max - m.z_min) / k]
    # an MPI run has one process per mesh (problems() insists), so a process carries its mesh's cells
    per_process: List[int] = list(cells) if setup.mode in ("parallel", "cluster") else []
    out: Dict[str, Any] = {
        "meshes": len(meshes), "cells": sum(cells), "cells_per_mesh": cells,
        "smallest_cell": min(sizes) if sizes else None, "largest_cell": max(sizes) if sizes else None,
        "cells_per_process": per_process,
        "errors": len(report.errors) if report is not None else None,
        "warnings": len(report.warnings) if report is not None else None,
    }
    busy = [c for c in per_process if c > 0]
    out["imbalance"] = max(busy) / (sum(busy) / len(busy)) if len(busy) > 1 else 1.0
    return out


def summary_lines(s: Dict[str, Any]) -> List[str]:
    """The summary as short lines; the ones that call for attention start with '!'."""
    if not s["meshes"]:
        return []
    lines = [f"{s['meshes']} mesh{'es' if s['meshes'] != 1 else ''}, {s['cells']:,} cells"
             + (f" (largest mesh {max(s['cells_per_mesh']):,})" if s["meshes"] > 1 else "")]
    if s["smallest_cell"] is not None:
        small, large = s["smallest_cell"], s["largest_cell"]
        lines.append(f"Cell size {_length(small)}" + (f" to {_length(large)}" if large > small * 1.0001 else ""))
    if s["cells_per_process"] and len(s["cells_per_process"]) > 1:
        per = s["cells_per_process"]
        text = f"Cells per process: {min(per):,} to {max(per):,}"
        if s["imbalance"] > _IMBALANCE:
            text = (f"! {text}: the busiest process has {s['imbalance']:.1f}x the average, and the run goes at its "
                    f"pace (split its meshes or balance the cell counts)")
        lines.append(text)
    if s["errors"] is not None:
        e, w = s["errors"], s["warnings"]
        lines.append(("! " if e else "") + f"Model checks: {e} error{'s' * (e != 1)}, {w} warning{'s' * (w != 1)}")
    return lines


def _length(metres: float) -> str:
    metres = float(f"{metres:.3g}")              # 0.09999999 (a 1 m mesh of 10 cells) reads as 0.1 m
    return f"{metres * 1000:.0f} mm" if metres < 0.1 else f"{metres:g} m"


def start(api: Any, setup: RunSetup, report: Any = None):
    """Begin the run. Returns the run handle (``api.solvers.status`` / ``stop`` / ``cancel``)."""
    found = problems(api, setup, report)
    if found:
        raise ValueError("; ".join(found))
    if setup.install:
        api.solvers.select(setup.install)
    if setup.mode in ("local", "parallel"):
        return api.solvers.run_local(setup.output_dir, setup.processes if setup.mode == "parallel" else 1,
                                     validate_first=setup.validate_first)
    if setup.mode == "cluster":
        return api.solvers.run_cluster(setup.hosts, setup.output_dir, validate_first=setup.validate_first)
    return api.solvers.run_cloud(setup.provider, setup.output_dir, setup.provider_config,
                                 num_processes=max(setup.processes, 1), validate_first=setup.validate_first,
                                 **setup.options)
