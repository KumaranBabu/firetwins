"""Cluster runs (RUN-04): host table, mesh assignment, validation and the MPI command.

Follows PyroSim's rules: one MPI process per mesh; meshes are handed to processes in mesh order and
processes to hosts in host-table order; the FDS file must sit in a folder every node sees under the
same path (on Windows a UNC path without spaces).
"""
from __future__ import annotations

import os
import re
import socket
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_LOCAL = {"localhost", "127.0.0.1", "::1"}


@dataclass
class ClusterHost:
    name: str
    processes: int = 1


def coerce_hosts(hosts: Sequence[Any]) -> List[ClusterHost]:
    """Accept ``ClusterHost``, ``(name, n)``, ``{"name":..,"processes":..}`` or ``"name:n"``."""
    out = []
    for h in hosts:
        if isinstance(h, ClusterHost):
            out.append(h)
        elif isinstance(h, dict):
            out.append(ClusterHost(str(h["name"]), int(h.get("processes", 1))))
        elif isinstance(h, (tuple, list)):
            out.append(ClusterHost(str(h[0]), int(h[1]) if len(h) > 1 else 1))
        elif isinstance(h, str):
            name, _, n = h.partition(":")
            out.append(ClusterHost(name.strip(), int(n) if n.strip() else 1))
        else:
            raise TypeError(f"cannot read a cluster host from {h!r}")
    return out


def is_local(name: str) -> bool:
    n = name.lower()
    return n in _LOCAL or n == socket.gethostname().lower()


def assign_meshes(hosts: Sequence[ClusterHost], mesh_count: int) -> List[Dict[str, Any]]:
    """Which meshes run on which host: process *r* runs mesh *r*; hosts take consecutive processes."""
    out, rank = [], 0
    for h in hosts:
        ranks = list(range(rank, rank + h.processes))
        out.append({"host": h.name, "ranks": ranks, "meshes": [r for r in ranks if r < mesh_count]})
        rank += h.processes
    return out


def validate(hosts: Sequence[ClusterHost], input_file: str, mesh_count: int,
             windows: Optional[bool] = None) -> List[str]:
    """Problems that would stop the run; an empty list means the setup is acceptable."""
    problems: List[str] = []
    windows = (os.name == "nt") if windows is None else windows
    if not hosts:
        problems.append("the host table is empty")
    seen = set()
    for h in hosts:
        if not _HOST_RE.match(h.name or ""):
            problems.append(f"{h.name!r} is not a valid host name")
        if h.processes < 1:
            problems.append(f"host {h.name} needs at least one process")
        if h.name.lower() in seen:
            problems.append(f"host {h.name} is listed twice")
        seen.add(h.name.lower())
    total = sum(max(h.processes, 0) for h in hosts)
    if mesh_count < 1:
        problems.append("the model has no meshes")
    elif total != mesh_count:
        problems.append(f"{total} processes for {mesh_count} meshes: FDS needs one process per mesh")
    remote = [h for h in hosts if not is_local(h.name)]
    if remote:
        if windows:
            if not input_file.startswith("\\\\"):
                problems.append("the FDS file must be on a shared UNC path (\\\\server\\share\\...) that every node can open")
            elif " " in input_file:
                problems.append("the UNC path must not contain spaces")
        elif not os.path.isabs(input_file):
            problems.append("the FDS file needs an absolute path that is the same on every node")
    return problems


def machinefile_text(hosts: Sequence[ClusterHost]) -> str:
    return "".join(f"{h.name}:{h.processes}\n" for h in hosts)


def build_command(mpiexec: str, fds_exe: str, input_file: str, hosts: Sequence[ClusterHost],
                  machinefile: str) -> List[str]:
    return [mpiexec, "-machinefile", machinefile, "-n", str(sum(h.processes for h in hosts)), fds_exe, input_file]
