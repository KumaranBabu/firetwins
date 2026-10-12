"""HPC job script generators: Slurm, PBS, LSF."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional


class SlurmJobScript:
    """Generate a SLURM batch script for an FDS simulation."""

    def generate(
        self,
        fds_input: str,
        output_dir: str,
        *,
        n_processes: int = 1,
        nodes: int = 1,
        tasks_per_node: Optional[int] = None,
        time_limit: str = "24:00:00",
        partition: Optional[str] = None,
        account: Optional[str] = None,
        job_name: Optional[str] = None,
        mem_per_cpu: Optional[str] = None,
        modules: Optional[List[str]] = None,
        fds_binary: str = "fds",
        mpiexec: str = "mpirun",
        extra_directives: Optional[List[str]] = None,
        conda_env: Optional[str] = None,
    ) -> str:
        """
        Generate a SLURM batch script.

        Returns
        -------
        str
            Complete bash script ready to pass to ``sbatch``.
        """
        fds_path = Path(fds_input).resolve()
        out_path  = Path(output_dir).resolve()
        stem      = fds_path.stem
        jname     = job_name or stem
        tpn       = tasks_per_node or max(1, n_processes // max(1, nodes))

        lines = ["#!/bin/bash", ""]
        lines += [f"#SBATCH --job-name={jname}",
                  f"#SBATCH --nodes={nodes}",
                  f"#SBATCH --ntasks-per-node={tpn}",
                  f"#SBATCH --ntasks={n_processes}",
                  f"#SBATCH --time={time_limit}"]
        if partition:
            lines.append(f"#SBATCH --partition={partition}")
        if account:
            lines.append(f"#SBATCH --account={account}")
        if mem_per_cpu:
            lines.append(f"#SBATCH --mem-per-cpu={mem_per_cpu}")
        lines += [f"#SBATCH --output={out_path}/{stem}_%j.out",
                  f"#SBATCH --error={out_path}/{stem}_%j.err"]
        if extra_directives:
            lines += extra_directives
        lines.append("")
        lines.append("# Environment")
        lines.append(f"mkdir -p {out_path}")

        if modules:
            lines.append("module purge")
            for mod in modules:
                lines.append(f"module load {mod}")

        if conda_env:
            lines.append(f"conda activate {conda_env}")

        lines += [
            "",
            "# Run FDS",
            f"cd {out_path}",
        ]
        if n_processes > 1:
            lines.append(
                f"{mpiexec} -n {n_processes} {fds_binary} {fds_path}"
            )
        else:
            lines.append(f"{fds_binary} {fds_path}")

        return "\n".join(lines) + "\n"


class PbsJobScript:
    """Generate a PBS/Torque batch script for an FDS simulation."""

    def generate(
        self,
        fds_input: str,
        output_dir: str,
        *,
        n_processes: int = 1,
        nodes: int = 1,
        ppn: int = 1,
        time_limit: str = "24:00:00",
        queue: Optional[str] = None,
        job_name: Optional[str] = None,
        modules: Optional[List[str]] = None,
        fds_binary: str = "fds",
        mpiexec: str = "mpirun",
        extra_directives: Optional[List[str]] = None,
    ) -> str:
        fds_path = Path(fds_input).resolve()
        out_path  = Path(output_dir).resolve()
        stem      = fds_path.stem
        jname     = job_name or stem

        lines = ["#!/bin/bash", ""]
        lines += [f"#PBS -N {jname}",
                  f"#PBS -l nodes={nodes}:ppn={ppn}",
                  f"#PBS -l walltime={time_limit}",
                  f"#PBS -o {out_path}/{stem}.out",
                  f"#PBS -e {out_path}/{stem}.err"]
        if queue:
            lines.append(f"#PBS -q {queue}")
        if extra_directives:
            lines += extra_directives
        lines.append("")
        lines.append(f"mkdir -p {out_path}")

        if modules:
            lines.append("module purge")
            for mod in modules:
                lines.append(f"module load {mod}")

        lines += [
            f"cd {out_path}",
        ]
        if n_processes > 1:
            lines.append(f"{mpiexec} -n {n_processes} {fds_binary} {fds_path}")
        else:
            lines.append(f"{fds_binary} {fds_path}")

        return "\n".join(lines) + "\n"


class LsfJobScript:
    """Generate an LSF (bsub) batch script for an FDS simulation."""

    def generate(
        self,
        fds_input: str,
        output_dir: str,
        *,
        n_processes: int = 1,
        time_limit: str = "24:00",
        queue: Optional[str] = None,
        job_name: Optional[str] = None,
        modules: Optional[List[str]] = None,
        fds_binary: str = "fds",
        mpiexec: str = "mpirun",
        extra_directives: Optional[List[str]] = None,
    ) -> str:
        fds_path = Path(fds_input).resolve()
        out_path  = Path(output_dir).resolve()
        stem      = fds_path.stem
        jname     = job_name or stem

        lines = ["#!/bin/bash", ""]
        lines += [f"#BSUB -J {jname}",
                  f"#BSUB -n {n_processes}",
                  f"#BSUB -W {time_limit}",
                  f"#BSUB -o {out_path}/{stem}_%J.out",
                  f"#BSUB -e {out_path}/{stem}_%J.err"]
        if queue:
            lines.append(f"#BSUB -q {queue}")
        if extra_directives:
            lines += extra_directives
        lines.append("")
        lines.append(f"mkdir -p {out_path}")

        if modules:
            lines.append("module purge")
            for mod in modules:
                lines.append(f"module load {mod}")

        lines += [f"cd {out_path}"]
        if n_processes > 1:
            lines.append(f"{mpiexec} -n {n_processes} {fds_binary} {fds_path}")
        else:
            lines.append(f"{fds_binary} {fds_path}")

        return "\n".join(lines) + "\n"
