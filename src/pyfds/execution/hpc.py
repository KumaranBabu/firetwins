"""
PyFDS HPC Cluster Job Submission
==================================
Generate and submit job scripts for SLURM, PBS/Torque, and LSF cluster
schedulers.  Optionally poll job status after submission.

Usage::

    from pyfds.execution.hpc import HpcManager

    hpc = HpcManager()
    job_id = hpc.submit_slurm(
        fds_input="building.fds",
        output_dir="/scratch/results",
        n_processes=16,
        nodes=2,
        time_limit="04:00:00",
        partition="compute",
        modules=["intel/2021", "openmpi/4.1", "fds/6.9"],
    )
    print("SLURM job submitted:", job_id)
    status = hpc.check_slurm(job_id)
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from .hpc_scripts import (  # noqa: F401  (re-exported)
    LsfJobScript,
    PbsJobScript,
    SlurmJobScript,
)


logger = logging.getLogger(__name__)


class HpcSubmitResult:
    """Holds the result of a cluster job submission."""

    def __init__(self, scheduler: str, job_id: Optional[str],
                 script: str, script_path: Optional[str] = None,
                 error: Optional[str] = None) -> None:
        self.scheduler   = scheduler
        self.job_id      = job_id
        self.script      = script
        self.script_path = script_path
        self.error       = error
        self.success     = job_id is not None and error is None

    def __repr__(self) -> str:
        return (f"<HpcSubmitResult scheduler={self.scheduler!r} "
                f"job_id={self.job_id!r} success={self.success}>")


class HpcManager:
    """
    High-level interface for HPC cluster job submission.

    Each ``submit_*`` method:
    1. Generates the appropriate scheduler script,
    2. Writes it to *script_dir* (or a temp file),
    3. Submits via ``sbatch`` / ``qsub`` / ``bsub`` if *dry_run=False*.

    Parameters
    ----------
    script_dir : str, optional
        Directory to write generated scripts (default: output_dir).
    dry_run : bool
        If True, generate the script but do not submit.
    """

    def __init__(
        self,
        script_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        self._script_dir = script_dir
        self._dry_run    = dry_run

    # ── SLURM ────────────────────────────────────────────────────────────────

    def submit_slurm(
        self,
        fds_input: str,
        output_dir: str,
        **kwargs,
    ) -> HpcSubmitResult:
        """Generate and optionally submit a SLURM job."""
        script = SlurmJobScript().generate(fds_input, output_dir, **kwargs)
        return self._submit(script, output_dir, fds_input, "sbatch", "SLURM")

    # ── PBS ──────────────────────────────────────────────────────────────────

    def submit_pbs(
        self,
        fds_input: str,
        output_dir: str,
        **kwargs,
    ) -> HpcSubmitResult:
        """Generate and optionally submit a PBS/Torque job."""
        script = PbsJobScript().generate(fds_input, output_dir, **kwargs)
        return self._submit(script, output_dir, fds_input, "qsub", "PBS")

    # ── LSF ──────────────────────────────────────────────────────────────────

    def submit_lsf(
        self,
        fds_input: str,
        output_dir: str,
        **kwargs,
    ) -> HpcSubmitResult:
        """Generate and optionally submit an LSF job."""
        script = LsfJobScript().generate(fds_input, output_dir, **kwargs)
        return self._submit(script, output_dir, fds_input, "bsub", "LSF")

    # ── Status polling ────────────────────────────────────────────────────────

    def check_slurm(self, job_id: str) -> str:
        """Query SLURM job state via ``squeue``."""
        return self._squeue(job_id)

    def check_pbs(self, job_id: str) -> str:
        """Query PBS job state via ``qstat``."""
        return self._qstat(job_id)

    def check_lsf(self, job_id: str) -> str:
        """Query LSF job state via ``bjobs``."""
        return self._bjobs(job_id)

    def cancel_slurm(self, job_id: str) -> bool:
        """Cancel a SLURM job via ``scancel``."""
        return self._run_cmd(["scancel", str(job_id)])

    def cancel_pbs(self, job_id: str) -> bool:
        """Cancel a PBS job via ``qdel``."""
        return self._run_cmd(["qdel", str(job_id)])

    def cancel_lsf(self, job_id: str) -> bool:
        """Cancel an LSF job via ``bkill``."""
        return self._run_cmd(["bkill", str(job_id)])

    # ── Script generation only ────────────────────────────────────────────────

    def generate_script(
        self,
        scheduler: str,
        fds_input: str,
        output_dir: str,
        **kwargs,
    ) -> str:
        """
        Return the job script as a string without submitting.

        Parameters
        ----------
        scheduler : {"slurm", "pbs", "lsf"}
        """
        s = scheduler.lower()
        if s == "slurm":
            return SlurmJobScript().generate(fds_input, output_dir, **kwargs)
        elif s in ("pbs", "torque"):
            return PbsJobScript().generate(fds_input, output_dir, **kwargs)
        elif s == "lsf":
            return LsfJobScript().generate(fds_input, output_dir, **kwargs)
        else:
            raise ValueError(f"Unknown scheduler {scheduler!r}. Use 'slurm', 'pbs', or 'lsf'.")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _submit(
        self, script: str, output_dir: str,
        fds_input: str, submit_cmd: str, scheduler: str,
    ) -> HpcSubmitResult:
        stem = Path(fds_input).stem
        script_dir = Path(self._script_dir or output_dir)
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"{stem}_{scheduler.lower()}.sh"
        script_path.write_text(script, encoding="utf-8")
        # Unix: make executable (no-op on Windows)
        try:
            script_path.chmod(0o755)
        except Exception:
            pass

        if self._dry_run:
            logger.info("HpcManager [dry_run]: %s script written to %s", scheduler, script_path)
            return HpcSubmitResult(scheduler, job_id=None, script=script,
                                   script_path=str(script_path))

        try:
            proc = subprocess.run(
                [submit_cmd, str(script_path)],
                capture_output=True, text=True, timeout=30,
            )
            job_id = self._parse_job_id(proc.stdout, scheduler)
            if job_id:
                logger.info("HpcManager: submitted %s job %s", scheduler, job_id)
                return HpcSubmitResult(scheduler, job_id=job_id, script=script,
                                       script_path=str(script_path))
            else:
                err = proc.stderr.strip() or proc.stdout.strip()
                logger.error("HpcManager: %s submission failed: %s", scheduler, err)
                return HpcSubmitResult(scheduler, job_id=None, script=script,
                                       script_path=str(script_path), error=err)
        except FileNotFoundError:
            err = f"{submit_cmd!r} not found — is the {scheduler} scheduler installed?"
            logger.error("HpcManager: %s", err)
            return HpcSubmitResult(scheduler, job_id=None, script=script,
                                   script_path=str(script_path), error=err)
        except subprocess.TimeoutExpired:
            err = f"{submit_cmd} timed out during submission"
            return HpcSubmitResult(scheduler, job_id=None, script=script,
                                   script_path=str(script_path), error=err)

    @staticmethod
    def _parse_job_id(output: str, scheduler: str) -> Optional[str]:
        s = scheduler.upper()
        if s == "SLURM":
            m = re.search(r"Submitted batch job (\d+)", output)
            return m.group(1) if m else None
        elif s == "PBS":
            m = re.search(r"(\d+\.?\S*)", output.strip())
            return m.group(1) if m else None
        elif s == "LSF":
            m = re.search(r"Job <(\d+)>", output)
            return m.group(1) if m else None
        return output.strip() or None

    def _squeue(self, job_id: str) -> str:
        try:
            r = subprocess.run(
                ["squeue", "-j", str(job_id), "-h", "-o", "%T"],
                capture_output=True, text=True, timeout=10,
            )
            return r.stdout.strip() or "UNKNOWN"
        except Exception as e:
            return f"ERROR: {e}"

    def _qstat(self, job_id: str) -> str:
        try:
            r = subprocess.run(
                ["qstat", str(job_id)],
                capture_output=True, text=True, timeout=10,
            )
            lines = r.stdout.strip().splitlines()
            if len(lines) >= 3:
                return lines[-1].split()[4] if len(lines[-1].split()) >= 5 else "UNKNOWN"
            return "UNKNOWN"
        except Exception as e:
            return f"ERROR: {e}"

    def _bjobs(self, job_id: str) -> str:
        try:
            r = subprocess.run(
                ["bjobs", str(job_id)],
                capture_output=True, text=True, timeout=10,
            )
            lines = r.stdout.strip().splitlines()
            if len(lines) >= 2:
                return lines[1].split()[2] if len(lines[1].split()) >= 3 else "UNKNOWN"
            return "UNKNOWN"
        except Exception as e:
            return f"ERROR: {e}"

    @staticmethod
    def _run_cmd(cmd: List[str]) -> bool:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False
