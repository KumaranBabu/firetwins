"""FDS installs, cluster and remote runs (C1)."""
from __future__ import annotations

from typing import List

from .base import ToolSpec

_STR = {"type": "string"}
_HOSTS = {"type": "array", "items": {"type": "string"},
          "description": "Host table in mesh order, each 'name:processes' (e.g. 'node1:4')."}


def _spec(name, description, props, required, handler, mutates=True):
    return ToolSpec(name=name, description=description,
                    input_schema={"type": "object", "properties": props, "required": required},
                    handler=handler, mutates=mutates)


def _handle(h):
    return {"id": h.id, "adapter": h.adapter, "state": h.state, "work_dir": h.work_dir, "message": h.message,
            "command": h.extra.get("command"), "plan": h.extra.get("plan")}


TOOLS: List[ToolSpec] = [
    _spec("list_fds_installs", "FDS builds found on this machine, with their versions.", {}, [],
          lambda api: [i.to_dict() for i in api.solvers.installs()], mutates=False),
    _spec("select_fds_install", "Use the named FDS build for runs; says whether it can read the project's syntax.",
          {"name": _STR}, ["name"], lambda api, name: api.solvers.select(name)),
    _spec("plan_cluster_run", "Which meshes each cluster host would run, and the problems that would stop a run.",
          {"hosts": _HOSTS}, ["hosts"], lambda api, hosts: api.solvers.cluster_plan(hosts), mutates=False),
    _spec("run_cluster", "Write the input to a folder visible to all nodes and start FDS over MPI on the host table "
          "(one process per mesh). dry_run only returns the command.",
          {"hosts": _HOSTS, "output_dir": _STR, "dry_run": {"type": "boolean"}}, ["hosts", "output_dir"],
          lambda api, hosts, output_dir, dry_run=False: _handle(api.solvers.run_cluster(hosts, output_dir, dry_run))),
    _spec("run_cloud", "Stage the input with a registered remote provider and start it there.",
          {"provider": _STR, "output_dir": _STR, "provider_config": {"type": "object"},
           "num_processes": {"type": "integer"}, "dry_run": {"type": "boolean"}}, ["provider", "output_dir"],
          lambda api, provider, output_dir, **kw: _handle(api.solvers.run_cloud(provider, output_dir, **kw))),
    _spec("remote_run_status", "State of a cluster or remote run started in this session.", {"id": _STR}, ["id"],
          lambda api, id: api.solvers.status(id), mutates=False),
    _spec("cancel_remote_run", "Cancel a cluster or remote run.", {"id": _STR}, ["id"],
          lambda api, id: api.solvers.cancel(id)),
    _spec("fetch_remote_results", "Bring a finished remote run's results into a folder.",
          {"id": _STR, "dest": _STR}, ["id", "dest"], lambda api, id, dest: api.solvers.fetch(id, dest)),
]
