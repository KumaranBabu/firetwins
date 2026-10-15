"""Solver adapters (C1): one interface for running FDS locally, on a cluster, or on a remote service.

``SolverAdapter`` is the Adapter/Strategy seam of decision D2. ``LocalAdapter`` wraps the existing
``SimulationRunner``; ``ClusterAdapter`` launches ``mpiexec -machinefile`` over a host table;
``CloudAdapter`` drives any ``CloudProvider`` (stage inputs, start, poll, fetch results). No vendor
cloud service is built in (their APIs and credentials cannot be verified here); a provider is a small
class registered with ``register_cloud_provider``. ``DirectoryProvider`` is the one shipped: a
shared or spool folder that runs the job with a local FDS.
"""
from __future__ import annotations

import os
import shutil
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import cluster as _cl

QUEUED, RUNNING, DONE, FAILED, CANCELLED, DRY_RUN = "queued", "running", "done", "failed", "cancelled", "dry_run"
FINISHED = {DONE, FAILED, CANCELLED, DRY_RUN}


class ClusterConfigError(ValueError):
    """The host table or file location cannot work; ``problems`` lists why."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


@dataclass
class RunRequest:
    input_file: str
    num_processes: int = 1
    fds_binary: Optional[str] = None
    mpiexec_binary: Optional[str] = None
    timeout: Optional[float] = None
    on_line: Optional[Callable[[str], None]] = None
    on_progress: Optional[Callable[[int, float, float], None]] = None
    dry_run: bool = False


@dataclass
class RunHandle:
    adapter: str
    work_dir: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: str = QUEUED
    returncode: Optional[int] = None
    message: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


class SolverAdapter(ABC):
    name = "solver"

    @abstractmethod
    def submit(self, request: RunRequest) -> RunHandle: ...

    @abstractmethod
    def status(self, handle: RunHandle) -> str: ...

    @abstractmethod
    def wait(self, handle: RunHandle, timeout: Optional[float] = None) -> bool: ...

    @abstractmethod
    def cancel(self, handle: RunHandle) -> None: ...

    def fetch(self, handle: RunHandle, dest: str) -> List[str]:
        """Bring results to *dest*. Local and cluster runs write beside the input, so nothing moves."""
        return []


class LocalAdapter(SolverAdapter):
    name = "local"

    def submit(self, request: RunRequest) -> RunHandle:
        from .runner import SimulationRunner
        work = str(Path(request.input_file).resolve().parent)
        handle = RunHandle(self.name, work)
        if request.dry_run:
            runner = SimulationRunner(request.fds_binary, request.mpiexec_binary)
            handle.state = DRY_RUN
            handle.extra["command"] = runner._build_command(str(Path(request.input_file).resolve()), request.num_processes)
            return handle
        return self._launch(handle, request, command=None)

    def _launch(self, handle: RunHandle, request: RunRequest, command) -> RunHandle:
        from .runner import SimulationRunner
        runner = SimulationRunner(request.fds_binary, request.mpiexec_binary)
        handle.extra["runner"] = runner
        handle.state = RUNNING

        def done(success: bool, rc: int) -> None:
            if handle.state == CANCELLED:
                return
            handle.returncode = rc
            handle.state = DONE if success else FAILED
            handle.message = runner.fds_error or ("" if success else f"FDS exited with code {rc}")

        runner.run(request.input_file, request.num_processes, on_line=request.on_line,
                   on_progress=request.on_progress, on_complete=done, timeout=request.timeout, command=command)
        return handle

    def status(self, handle: RunHandle) -> str:
        return handle.state

    def wait(self, handle: RunHandle, timeout: Optional[float] = None) -> bool:
        runner = handle.extra.get("runner")
        return runner.wait(timeout) if runner else True

    def cancel(self, handle: RunHandle) -> None:
        runner = handle.extra.get("runner")
        if runner and handle.state == RUNNING:
            handle.state = CANCELLED
            runner.cancel()


class ClusterAdapter(LocalAdapter):
    """FDS over MPI on several machines. ``hosts`` is the host table (name, processes), in mesh order."""
    name = "cluster"

    def __init__(self, hosts: Sequence[Any], mesh_count: int, windows: Optional[bool] = None) -> None:
        self.hosts = _cl.coerce_hosts(hosts)
        self.mesh_count = int(mesh_count)
        self.windows = windows

    def plan(self) -> List[Dict[str, Any]]:
        """Which meshes each host will run (the 'Assigned Meshes' preview)."""
        return _cl.assign_meshes(self.hosts, self.mesh_count)

    def submit(self, request: RunRequest) -> RunHandle:
        from .runner import SimulationRunner
        input_file = str(Path(request.input_file).resolve()) if not request.input_file.startswith("\\\\") \
            else request.input_file
        problems = _cl.validate(self.hosts, input_file, self.mesh_count, self.windows)
        if problems:
            raise ClusterConfigError(problems)
        runner = SimulationRunner(request.fds_binary, request.mpiexec_binary)
        work = os.path.dirname(input_file)
        stem = Path(input_file).stem
        machinefile = os.path.join(work, f"{stem}.hosts")
        cmd = _cl.build_command(runner._mpiexec_binary, runner._fds_binary, input_file, self.hosts, machinefile)
        handle = RunHandle(self.name, work, extra={"command": cmd, "machinefile": machinefile, "plan": self.plan()})
        if request.dry_run:
            handle.state = DRY_RUN
            return handle
        Path(machinefile).write_text(_cl.machinefile_text(self.hosts), encoding="utf-8")
        request.num_processes = sum(h.processes for h in self.hosts)
        return self._launch(handle, request, command=cmd)


# -- cloud / remote ----------------------------------------------------------------------------
class CloudProvider(ABC):
    """What a remote service must do. All calls are blocking and short; the run itself is remote."""
    name = "provider"

    @abstractmethod
    def upload(self, input_file: str) -> str:
        """Stage the input; returns the remote job id."""

    @abstractmethod
    def start(self, remote_id: str, options: Dict[str, Any]) -> None: ...

    @abstractmethod
    def status(self, remote_id: str) -> str:
        """One of queued, running, done, failed, cancelled."""

    @abstractmethod
    def download(self, remote_id: str, dest: str) -> List[str]: ...

    @abstractmethod
    def cancel(self, remote_id: str) -> None: ...


_PROVIDERS: Dict[str, Callable[..., CloudProvider]] = {}


def register_cloud_provider(name: str, factory: Callable[..., CloudProvider]) -> None:
    _PROVIDERS[name] = factory


def cloud_providers() -> List[str]:
    return sorted(_PROVIDERS)


def get_cloud_provider(name: str, **config: Any) -> CloudProvider:
    try:
        return _PROVIDERS[name](**config)
    except KeyError:
        raise KeyError(f"unknown cloud provider {name!r}; registered: {', '.join(cloud_providers()) or 'none'}") from None


class CloudAdapter(SolverAdapter):
    name = "cloud"

    def __init__(self, provider: CloudProvider, **options: Any) -> None:
        self.provider = provider
        self.options = options          # e.g. fds_version, vcpus, memory_gb_per_vcpu

    def submit(self, request: RunRequest) -> RunHandle:
        work = str(Path(request.input_file).resolve().parent)
        handle = RunHandle(self.name, work, extra={"provider": self.provider.name, "options": dict(self.options)})
        if request.dry_run:
            handle.state = DRY_RUN
            return handle
        remote = self.provider.upload(request.input_file)
        handle.extra["remote_id"] = remote
        self.provider.start(remote, {**self.options, "num_processes": request.num_processes})
        handle.state = QUEUED
        return handle

    def status(self, handle: RunHandle) -> str:
        if handle.state in FINISHED:
            return handle.state
        state = self.provider.status(handle.extra["remote_id"])
        if state not in (QUEUED, RUNNING, DONE, FAILED, CANCELLED):
            raise ValueError(f"provider {self.provider.name} reported unknown state {state!r}")
        handle.state = state
        return state

    def wait(self, handle: RunHandle, timeout: Optional[float] = None) -> bool:
        import time
        end = None if timeout is None else time.monotonic() + timeout
        while self.status(handle) not in FINISHED:
            if end is not None and time.monotonic() > end:
                return False
            time.sleep(0.2)
        return True

    def cancel(self, handle: RunHandle) -> None:
        if handle.state not in FINISHED:
            self.provider.cancel(handle.extra["remote_id"])
            handle.state = CANCELLED

    def fetch(self, handle: RunHandle, dest: str) -> List[str]:
        if self.status(handle) not in (DONE, FAILED):
            raise RuntimeError("results can be fetched once the run has finished")
        return self.provider.download(handle.extra["remote_id"], dest)


class DirectoryProvider(CloudProvider):
    """A spool or shared folder acting as the 'remote': each job gets a sub-folder and runs with the
    local FDS. Useful for a shared batch drive, and to exercise the whole upload/poll/fetch path."""
    name = "directory"

    def __init__(self, root: str, fds_binary: Optional[str] = None, mpiexec_binary: Optional[str] = None) -> None:
        self.root = Path(root)
        self.fds_binary = fds_binary
        self.mpiexec_binary = mpiexec_binary
        self._jobs: Dict[str, RunHandle] = {}
        self._inputs: Dict[str, str] = {}
        self._adapter = LocalAdapter()
        self._lock = threading.Lock()

    def upload(self, input_file: str) -> str:
        rid = uuid.uuid4().hex[:12]
        folder = self.root / rid
        folder.mkdir(parents=True, exist_ok=False)
        shutil.copy2(input_file, folder / Path(input_file).name)
        self._inputs[rid] = Path(input_file).name
        return rid

    def start(self, remote_id: str, options: Dict[str, Any]) -> None:
        folder = self.root / remote_id
        req = RunRequest(str(folder / self._inputs[remote_id]), int(options.get("num_processes", 1)),
                         self.fds_binary, self.mpiexec_binary)
        with self._lock:
            self._jobs[remote_id] = self._adapter.submit(req)

    def status(self, remote_id: str) -> str:
        job = self._jobs.get(remote_id)
        if job is None:
            return QUEUED
        return job.state

    def download(self, remote_id: str, dest: str) -> List[str]:
        folder = self.root / remote_id
        out = []
        Path(dest).mkdir(parents=True, exist_ok=True)
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.name != self._inputs.get(remote_id):
                shutil.copy2(f, Path(dest) / f.name)
                out.append(f.name)
        return out

    def cancel(self, remote_id: str) -> None:
        job = self._jobs.get(remote_id)
        if job is not None:
            self._adapter.cancel(job)


register_cloud_provider("directory", DirectoryProvider)
