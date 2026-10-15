"""Crash-isolated worker processes (the bulkhead, decision D2).

Heavy or fragile native code (CAD parsers, geometry kernels) can crash the interpreter or run
forever. ``run_isolated("pkg.module:function", *args)`` runs it in a separate *spawned* process: if
that process dies or overruns, the caller gets an exception and the application keeps running.
Arguments and the result travel by pickle, so they must be picklable (this is our own child process,
not untrusted input).
"""
from __future__ import annotations

import importlib
import multiprocessing
import traceback
from typing import Any


class WorkerError(RuntimeError):
    """The function raised; ``remote_type`` and ``remote_traceback`` describe what happened in the worker."""

    def __init__(self, message: str, remote_type: str = "", remote_traceback: str = "") -> None:
        super().__init__(message)
        self.remote_type = remote_type
        self.remote_traceback = remote_traceback


class WorkerCrashed(RuntimeError):
    """The worker process died without answering (segfault, out of memory, killed)."""

    def __init__(self, exitcode) -> None:
        super().__init__(f"worker process crashed (exit code {exitcode})")
        self.exitcode = exitcode


class WorkerTimeout(TimeoutError):
    """The worker did not answer in time and was killed."""


def _resolve(target: str):
    if ":" not in target:
        raise ValueError("target must look like 'package.module:function'")
    mod, _, name = target.partition(":")
    obj = importlib.import_module(mod)
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


def _child(conn, target, args, kwargs) -> None:
    try:
        result = _resolve(target)(*args, **kwargs)
        conn.send(("ok", result))
    except BaseException as exc:      # report everything, including SystemExit from the function
        try:
            conn.send(("error", type(exc).__name__, str(exc), traceback.format_exc()))
        except Exception:
            pass
    finally:
        conn.close()


def run_isolated(target: str, *args: Any, timeout: float = 300.0, **kwargs: Any) -> Any:
    """Call ``target`` (``"package.module:function"``) in a separate process and return its result.

    Raises ``WorkerError`` if the function raised, ``WorkerCrashed`` if the process died, and
    ``WorkerTimeout`` (after killing it) if it took longer than *timeout* seconds."""
    _resolve(target)                                   # fail fast, in this process, on a typo
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child, target, args, kwargs), daemon=True)
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout):
            proc.kill()
            proc.join(5)
            raise WorkerTimeout(f"{target} did not finish within {timeout:g} s")
        try:
            msg = parent.recv()
        except (EOFError, OSError):
            proc.join(5)
            raise WorkerCrashed(proc.exitcode) from None
    finally:
        parent.close()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
    if msg[0] == "ok":
        return msg[1]
    raise WorkerError(f"{msg[1]}: {msg[2]}", msg[1], msg[3])
