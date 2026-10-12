"""
PyFDS Batch Study JSON Config Validator
=========================================
Provides a typed, validated representation of the JSON file consumed by
``pyfds batch`` and ``BatchExecutor``.

The validator gives engineers clear, actionable error messages before any
simulations are launched.

Config file format
------------------
::

    {
        "name": "hrr_sensitivity",
        "base_fds_file": "base_case.fds",
        "output_root": "batch_results/",
        "max_workers": 4,
        "vary": [
            {"path": "params.t_end",  "values": [30, 60, 120], "label": "T_END"},
            {"path": "surfaces[0].heat_release_rate", "values": [250, 500, 1000]}
        ],
        "fix": {
            "misc.tmpa": 20.0
        },
        "run": true,
        "fds_binary": "/path/to/fds"
    }

Required keys: ``name``, ``vary`` (non-empty list).
Optional keys: ``base_fds_file``, ``output_root``, ``max_workers``, ``fix``,
               ``run``, ``fds_binary``.

Usage::

    from pyfds.execution.batch_config import BatchStudyConfig

    cfg = BatchStudyConfig.from_file("study.json")
    # or
    cfg = BatchStudyConfig.from_dict(data)

    study, executor = cfg.build()
    report = executor.run(study)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Typed config
# ---------------------------------------------------------------------------

@dataclass
class AxisConfig:
    """One vary-axis definition."""
    path: str
    values: List[Any]
    label: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict, idx: int) -> "AxisConfig":
        errors = []
        if "path" not in d or not isinstance(d["path"], str) or not d["path"].strip():
            errors.append(f"vary[{idx}].path must be a non-empty string")
        if "values" not in d or not isinstance(d["values"], list) or not d["values"]:
            errors.append(f"vary[{idx}].values must be a non-empty list")
        if errors:
            raise BatchConfigError("\n".join(errors))
        return cls(
            path=d["path"].strip(),
            values=d["values"],
            label=d.get("label"),
        )


@dataclass
class BatchStudyConfig:
    """
    Fully-validated representation of a batch study config file.

    Attributes
    ----------
    name : str
        Human-readable study name.
    base_fds_file : str
        Path to the base ``.fds`` or ``.pyfds`` file.  May be empty when the
        study generates project programmatically.
    output_root : str
        Root directory for per-variant output subdirectories.
    max_workers : int
        Parallel simulation slots.
    axes : list[AxisConfig]
        Parameters to vary (Cartesian product defines variants).
    fixed : dict
        Parameters to set to a constant value in all variants.
    run_simulations : bool
        Whether to actually execute FDS (False = dry run / write-only).
    fds_binary : str
        Override path to the FDS executable.
    """
    name: str
    base_fds_file: str = ""
    output_root: str = "batch_results"
    max_workers: int = 2
    axes: List[AxisConfig] = field(default_factory=list)
    fixed: Dict[str, Any] = field(default_factory=dict)
    run_simulations: bool = True
    fds_binary: str = ""

    # ── Factories ──────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, filepath: str) -> "BatchStudyConfig":
        """
        Load and validate from a JSON file.

        Raises :class:`BatchConfigError` with a descriptive message on failure.
        """
        path = Path(filepath)
        if not path.exists():
            raise BatchConfigError(f"Config file not found: {filepath}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BatchConfigError(f"Invalid JSON in {filepath}: {exc}") from exc
        if not isinstance(data, dict):
            raise BatchConfigError(f"Config must be a JSON object, got {type(data).__name__}")
        return cls.from_dict(data, source=filepath)

    @classmethod
    def from_dict(cls, data: dict, source: str = "<dict>") -> "BatchStudyConfig":
        """
        Validate *data* and return a :class:`BatchStudyConfig`.

        Raises :class:`BatchConfigError` with all discovered problems listed.
        """
        errors: List[str] = []

        # ── Required ──────────────────────────────────────────────────────────
        name = data.get("name", "")
        if not isinstance(name, str) or not name.strip():
            errors.append("'name' must be a non-empty string")

        vary_raw = data.get("vary", [])
        if not isinstance(vary_raw, list) or not vary_raw:
            errors.append("'vary' must be a non-empty list of axis definitions")
        elif not all(isinstance(a, dict) for a in vary_raw):
            errors.append("Each entry in 'vary' must be a JSON object")

        # ── Optional ─────────────────────────────────────────────────────────
        base_fds = data.get("base_fds_file", "")
        if not isinstance(base_fds, str):
            errors.append("'base_fds_file' must be a string path")

        output_root = data.get("output_root", "batch_results")
        if not isinstance(output_root, str):
            errors.append("'output_root' must be a string path")

        max_workers = data.get("max_workers", 2)
        if not isinstance(max_workers, int) or max_workers < 1:
            errors.append("'max_workers' must be a positive integer")

        fixed = data.get("fix", {})
        if not isinstance(fixed, dict):
            errors.append("'fix' must be a JSON object (key: value pairs)")

        run_sims = data.get("run", True)
        if not isinstance(run_sims, bool):
            errors.append("'run' must be a boolean (true/false)")

        fds_bin = data.get("fds_binary", "")
        if not isinstance(fds_bin, str):
            errors.append("'fds_binary' must be a string path")
        elif fds_bin and not Path(fds_bin).exists():
            errors.append(f"'fds_binary' path does not exist: {fds_bin}")

        # ── Abort early on structural errors ──────────────────────────────────
        if errors:
            raise BatchConfigError(
                f"Batch config validation failed ({source}):\n"
                + "\n".join(f"  • {e}" for e in errors)
            )

        # ── Parse axes (may emit per-axis errors) ─────────────────────────────
        axes: List[AxisConfig] = []
        axis_errors: List[str] = []
        for i, ax in enumerate(vary_raw):
            try:
                axes.append(AxisConfig.from_dict(ax, i))
            except BatchConfigError as exc:
                axis_errors.append(str(exc))

        if axis_errors:
            raise BatchConfigError(
                f"Batch config axis errors ({source}):\n"
                + "\n".join(f"  • {e}" for e in axis_errors)
            )

        # ── Warn about unknown keys ───────────────────────────────────────────
        _known = {"name", "base_fds_file", "output_root", "max_workers",
                  "vary", "fix", "run", "fds_binary"}
        unknown = set(data.keys()) - _known
        if unknown:
            import warnings
            warnings.warn(
                f"BatchStudyConfig: unknown keys in config will be ignored: {sorted(unknown)}",
                stacklevel=3,
            )

        return cls(
            name=name.strip(),
            base_fds_file=base_fds,
            output_root=output_root,
            max_workers=int(max_workers),
            axes=axes,
            fixed=dict(fixed),
            run_simulations=bool(run_sims),
            fds_binary=fds_bin,
        )

    # ── Build executable objects ─────────────────────────────────────────────

    def build(self) -> Tuple[Any, Any]:
        """
        Construct a ``(ParametricStudy, BatchExecutor)`` pair ready to run.

        Returns
        -------
        tuple
            ``(study, executor)`` — call ``executor.run(study)`` to start.
        """
        from pyfds.execution.batch import ParametricStudy, BatchExecutor

        study = ParametricStudy(
            name=self.name,
            base_fds_file=self.base_fds_file,
        )
        for axis in self.axes:
            study.vary(axis.path, axis.values, label=axis.label)
        for key, val in self.fixed.items():
            study.fix(key, val)

        executor = BatchExecutor(
            output_root=self.output_root,
            max_workers=self.max_workers,
            run_simulations=self.run_simulations,
            fds_binary=self.fds_binary or None,
        )
        return study, executor

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Round-trip to JSON-serialisable dict."""
        d: dict = {
            "name": self.name,
            "vary": [
                {
                    "path": ax.path,
                    "values": ax.values,
                    **({"label": ax.label} if ax.label else {}),
                }
                for ax in self.axes
            ],
        }
        if self.base_fds_file:
            d["base_fds_file"] = self.base_fds_file
        if self.output_root != "batch_results":
            d["output_root"] = self.output_root
        if self.max_workers != 2:
            d["max_workers"] = self.max_workers
        if self.fixed:
            d["fix"] = self.fixed
        if not self.run_simulations:
            d["run"] = False
        if self.fds_binary:
            d["fds_binary"] = self.fds_binary
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @property
    def n_variants(self) -> int:
        """Total number of variants (Cartesian product of all axis values)."""
        result = 1
        for ax in self.axes:
            result *= len(ax.values)
        return result

    def __repr__(self) -> str:
        return (f"<BatchStudyConfig name={self.name!r} "
                f"axes={len(self.axes)} variants={self.n_variants}>")


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class BatchConfigError(ValueError):
    """Raised when a batch study config file fails validation."""
