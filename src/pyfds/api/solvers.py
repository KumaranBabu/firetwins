"""Where and how FDS runs: ``api.solvers`` (RUN-04, RUN-05, RUN-07, bulkhead).

* installed FDS builds and the one in use (``installs`` / ``select``);
* cluster runs over a host table (``run_cluster``) and remote runs through a registered
  ``CloudProvider`` (``run_cloud``), both behind the ``SolverAdapter`` interface;
* ``call_isolated`` runs a function in a separate process so a crash cannot take the app down.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pyfds.execution import adapters as _ad
from pyfds.execution import cluster as _cl
from pyfds.execution import installs as _in
from pyfds.execution.isolated import run_isolated


class SolverManager:
    def __init__(self, api) -> None:
        self._api = api
        self._handles: Dict[str, Any] = {}      # handle id -> (adapter, handle)

    @staticmethod
    def _cfg():
        from pyfds.core.config import get_config
        return get_config()

    # -- installed builds (RUN-07) -----------------------------------------------------------
    def installs(self, probe: bool = True) -> List[_in.FdsInstall]:
        cfg = self._cfg()
        extra = list(cfg.get("fds_install_dirs", []) or []) + list(cfg.get("fds_installs", []) or [])
        return _in.discover(extra, probe=probe)

    def add_install(self, path: str) -> _in.FdsInstall:
        """Remember an FDS executable (or a folder holding one) that discovery would not find."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        found = _in.discover([str(p)])
        match = [i for i in found if str(Path(i.path).resolve()).lower().startswith(str(p.resolve()).lower())]
        if not match:
            raise ValueError(f"no FDS executable found at {path}")
        if match[0].version is None:
            raise ValueError(f"{match[0].path} did not report an FDS version, so it does not look like FDS")
        cfg = self._cfg()
        known = list(cfg.get("fds_installs", []) or [])
        if str(p) not in known:
            cfg.set("fds_installs", known + [str(p)])
        return match[0]

    def select(self, name: str) -> Dict[str, Any]:
        """Use the named install for runs. Returns it with a compatibility verdict for the project."""
        for inst in self.installs():
            if inst.name == name:
                cfg = self._cfg()
                cfg.set("fds_binary", inst.path)
                if inst.mpiexec:
                    cfg.set("mpiexec_binary", inst.mpiexec)
                cfg.set("fds_install_name", inst.name)
                ok, msg = _in.compatibility(inst.version, self._api.project.fds_version)
                return {**inst.to_dict(), "compatible": ok, "message": msg}
        raise KeyError(f"no FDS install named {name!r}; see installs()")

    def selected(self) -> Dict[str, Any]:
        cfg = self._cfg()
        path = cfg.get("fds_binary")
        version = _in.probe_version(path) if path and Path(path).is_file() else None
        ok, msg = _in.compatibility(version, self._api.project.fds_version)
        return {"name": cfg.get("fds_install_name"), "path": path, "version": version,
                "compatible": ok, "message": msg}

    # -- writing the input -------------------------------------------------------------------
    def _write_input(self, output_dir: str, validate_first: bool) -> str:
        if validate_first:
            self._api.validation.gate()
        from pyfds.io.fds_writer import FdsWriter
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{self._api.project.chid}.fds"
        FdsWriter().write(self._api.project, str(path))
        return str(path)

    def _request(self, input_file: str, num_processes: int, dry_run: bool, timeout=None) -> _ad.RunRequest:
        cfg = self._cfg()
        fds, mpi = cfg.get("fds_binary"), cfg.get("mpiexec_binary")
        if not (fds and Path(fds).is_file()):                 # the configured binary is missing: use a detected install
            found = self.installs(probe=False)
            if found:
                fds, mpi = found[0].path, found[0].mpiexec or mpi
        return _ad.RunRequest(input_file, num_processes, fds, mpi, timeout, dry_run=dry_run)

    def _keep(self, adapter, handle):
        handle.extra.setdefault("chid", self._api.project.chid)
        handle.extra.setdefault("t_end", self._api.project.params.t_end)
        self._handles[handle.id] = (adapter, handle)
        return handle

    def progress(self, handle) -> Dict[str, Any]:
        """How far a run has got, from the files in its case folder (which may be on a network share): ``time``,
        ``step``, ``t_end``, ``fraction``, ``finished``, ``idle`` and a ``text`` such as ``"12.3 / 60 s (20%)"``."""
        from pyfds.execution.progress import describe, read_progress
        _adapter, h = self._pair(handle)
        info = read_progress(h.work_dir, h.extra.get("chid", self._api.project.chid), h.extra.get("t_end"))
        info["text"] = describe(info)
        return info

    # -- local and parallel runs, stopping, model preview (F6) -----------------------------------------
    def run_local(self, output_dir: str, num_processes: int = 1, dry_run: bool = False,
                  validate_first: bool = True, timeout: Optional[float] = None, on_line=None):
        """Write the input to *output_dir* and run FDS on this machine, with *num_processes* MPI processes
        (more than one needs a mesh for each). Returns a run handle for ``status`` / ``stop`` / ``cancel``."""
        n_meshes = len(self._api.project.meshes)
        if num_processes < 1:
            raise ValueError("at least one process is needed")
        if num_processes > 1 and num_processes != n_meshes:
            raise ValueError(f"{num_processes} processes for {n_meshes} meshes: FDS needs one process per mesh")
        input_file = self._write_input(output_dir, validate_first)
        adapter = _ad.LocalAdapter()
        request = self._request(input_file, num_processes, dry_run, timeout)
        request.on_line = on_line
        handle = adapter.submit(request)
        handle.extra["chid"] = self._api.project.chid
        return self._keep(adapter, handle)

    def stop(self, handle) -> str:
        """Ask a running FDS to stop cleanly: it finishes the time step, writes a restart file and exits (so the
        run can be resumed). FDS has no pause. Returns the stop file's path."""
        adapter, h = self._pair(handle)
        if h.adapter not in ("local", "cluster"):
            raise ValueError("only local and cluster runs can be stopped this way; use cancel()")
        if h.state != _ad.RUNNING:
            raise ValueError(f"the run is not running (it is {h.state})")
        stop_file = Path(h.work_dir) / f"{h.extra.get('chid', self._api.project.chid)}.stop"
        stop_file.write_text("stop\n", encoding="utf-8")
        h.extra["stop_requested"] = True
        return str(stop_file)

    def preview_model(self, work_dir: str, timeout: float = 120.0) -> str:
        """Run FDS for zero simulated time in *work_dir* so Smokeview and the results viewer can show the geometry
        before any real run. The project is not changed. Returns the ``.smv`` path."""
        text = self._api.fds_text()
        chid = self._api.project.chid
        preview = f"{chid}_preview"
        text = re.sub(r"(?i)\bCHID\s*=\s*'[^']*'", f"CHID='{preview}'", text, count=1)
        text, n = re.subn(r"(?i)\bT_END\s*=\s*[-+0-9.eE]+", "T_END=0.0", text, count=1)
        if not n:
            text = text.replace("&TAIL", "&TIME T_END=0.0 /\n&TAIL", 1)
        out = Path(work_dir)
        out.mkdir(parents=True, exist_ok=True)
        fds_file = out / f"{preview}.fds"
        fds_file.write_text(text, encoding="utf-8")
        adapter = _ad.LocalAdapter()
        handle = adapter.submit(self._request(str(fds_file), 1, False, timeout))
        adapter.wait(handle, timeout)
        smv = out / f"{preview}.smv"
        if handle.state != _ad.DONE or not smv.is_file():
            raise RuntimeError(handle.message or "FDS did not produce a preview of the model")
        return str(smv)

    # -- cluster (RUN-04) ----------------------------------------------------------------------
    def cluster_plan(self, hosts: Sequence[Any], input_file: Optional[str] = None) -> Dict[str, Any]:
        """The 'Assigned Meshes' preview plus the problems that would stop a run."""
        hs = _cl.coerce_hosts(hosts)
        n = len(self._api.project.meshes)
        return {"assignment": _cl.assign_meshes(hs, n),
                "problems": _cl.validate(hs, input_file or str(Path.cwd()), n)}

    def run_cluster(self, hosts: Sequence[Any], output_dir: str, dry_run: bool = False,
                    validate_first: bool = True, timeout: Optional[float] = None):
        """Write the input to *output_dir* (it must be visible to every node) and start it with MPI over the
        host table. ``dry_run`` returns the command and plan without launching."""
        input_file = self._write_input(output_dir, validate_first)
        adapter = _ad.ClusterAdapter(hosts, len(self._api.project.meshes))
        handle = adapter.submit(self._request(input_file, 1, dry_run, timeout))
        handle.extra["chid"] = self._api.project.chid
        return self._keep(adapter, handle)

    # -- cloud / remote (RUN-05) ------------------------------------------------------------------
    def register_cloud_provider(self, name: str, factory) -> None:
        _ad.register_cloud_provider(name, factory)

    def cloud_providers(self) -> List[str]:
        return _ad.cloud_providers()

    def run_cloud(self, provider: str, output_dir: str, provider_config: Optional[Dict[str, Any]] = None,
                  num_processes: int = 1, dry_run: bool = False, validate_first: bool = True, **options: Any):
        """Stage the input with a registered provider and start it there. *options* (fds_version, vcpus,
        memory_gb_per_vcpu ...) go to the provider unchanged."""
        input_file = self._write_input(output_dir, validate_first)
        adapter = _ad.CloudAdapter(_ad.get_cloud_provider(provider, **(provider_config or {})), **options)
        handle = adapter.submit(self._request(input_file, num_processes, dry_run))
        return self._keep(adapter, handle)

    # -- handles ---------------------------------------------------------------------------------
    def _pair(self, handle):
        hid = getattr(handle, "id", handle)
        try:
            return self._handles[hid]
        except KeyError:
            raise KeyError(f"no run {hid!r}") from None

    def status(self, handle) -> str:
        adapter, h = self._pair(handle)
        return adapter.status(h)

    def wait(self, handle, timeout: Optional[float] = None) -> bool:
        adapter, h = self._pair(handle)
        return adapter.wait(h, timeout)

    def cancel(self, handle) -> None:
        adapter, h = self._pair(handle)
        adapter.cancel(h)

    def fetch(self, handle, dest: str) -> List[str]:
        adapter, h = self._pair(handle)
        return adapter.fetch(h, dest)

    # -- bulkhead ---------------------------------------------------------------------------------
    def call_isolated(self, target: str, *args: Any, timeout: float = 300.0, **kwargs: Any) -> Any:
        """Run ``"package.module:function"`` in a separate process; a crash or overrun raises
        ``WorkerCrashed`` / ``WorkerTimeout`` instead of ending the application."""
        return run_isolated(target, *args, timeout=timeout, **kwargs)
