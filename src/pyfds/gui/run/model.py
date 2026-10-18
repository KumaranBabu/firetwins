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


def problems(api: Any, setup: RunSetup) -> List[str]:
    """Reasons the run cannot start; an empty list means it can."""
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
    if setup.validate_first and n and not api.validation.can_run():
        out.append("the model has errors; see Model Checks")
    return out


def start(api: Any, setup: RunSetup):
    """Begin the run. Returns the run handle (``api.solvers.status`` / ``stop`` / ``cancel``)."""
    found = problems(api, setup)
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
