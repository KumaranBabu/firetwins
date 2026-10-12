"""Unit tests — pyfds.execution.hpc (HpcManager, script generators)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyfds.execution.hpc import (
    HpcManager,
    HpcSubmitResult,
    SlurmJobScript,
    PbsJobScript,
    LsfJobScript,
)


FDS_INPUT = "/scratch/runs/building.fds"
OUTPUT_DIR = "/scratch/runs/out"


# ---------------------------------------------------------------------------
# SlurmJobScript
# ---------------------------------------------------------------------------

class TestSlurmJobScript:
    def _gen(self, **kwargs):
        return SlurmJobScript().generate(FDS_INPUT, OUTPUT_DIR, **kwargs)

    def test_shebang(self):
        assert self._gen().startswith("#!/bin/bash")

    def test_job_name_directive(self):
        script = self._gen(job_name="my_job")
        assert "#SBATCH --job-name=my_job" in script

    def test_job_name_defaults_to_stem(self):
        script = self._gen()
        assert "#SBATCH --job-name=building" in script

    def test_nodes_directive(self):
        script = self._gen(nodes=4)
        assert "#SBATCH --nodes=4" in script

    def test_ntasks_directive(self):
        script = self._gen(n_processes=16)
        assert "#SBATCH --ntasks=16" in script

    def test_time_directive(self):
        script = self._gen(time_limit="08:00:00")
        assert "#SBATCH --time=08:00:00" in script

    def test_partition_included_when_given(self):
        script = self._gen(partition="compute")
        assert "#SBATCH --partition=compute" in script

    def test_partition_absent_when_not_given(self):
        script = self._gen()
        assert "--partition" not in script

    def test_account_included(self):
        script = self._gen(account="proj123")
        assert "#SBATCH --account=proj123" in script

    def test_mem_per_cpu_included(self):
        script = self._gen(mem_per_cpu="4G")
        assert "#SBATCH --mem-per-cpu=4G" in script

    def test_output_log_paths(self):
        script = self._gen()
        resolved = str(Path(OUTPUT_DIR).resolve())
        assert resolved in script
        assert "_j.out" in script or "%j.out" in script

    def test_modules_included(self):
        script = self._gen(modules=["intel/2021", "openmpi/4.1"])
        assert "module load intel/2021" in script
        assert "module load openmpi/4.1" in script

    def test_module_purge_before_loads(self):
        script = self._gen(modules=["fds/6.9"])
        lines = script.splitlines()
        purge_idx  = next((i for i, l in enumerate(lines) if "module purge" in l), None)
        load_idx   = next((i for i, l in enumerate(lines) if "module load fds" in l), None)
        assert purge_idx is not None and load_idx is not None
        assert purge_idx < load_idx

    def test_conda_env_included(self):
        script = self._gen(conda_env="fds_env")
        assert "conda activate fds_env" in script

    def test_mpi_run_when_n_processes_gt_1(self):
        script = self._gen(n_processes=4)
        assert "mpirun -n 4" in script or "mpiexec" in script

    def test_no_mpi_when_single_process(self):
        script = self._gen(n_processes=1)
        assert "mpirun" not in script
        assert "mpiexec" not in script

    def test_extra_directives_included(self):
        script = self._gen(extra_directives=["#SBATCH --constraint=avx512"])
        assert "#SBATCH --constraint=avx512" in script

    def test_fds_input_path_in_run_line(self):
        script = self._gen()
        assert "building.fds" in script

    def test_cd_to_output_dir(self):
        script = self._gen()
        resolved = str(Path(OUTPUT_DIR).resolve())
        assert f"cd {resolved}" in script


# ---------------------------------------------------------------------------
# SlurmJobScript — additional edge cases
# ---------------------------------------------------------------------------

class TestSlurmEdgeCases:
    def _gen(self, **kwargs):
        return SlurmJobScript().generate(FDS_INPUT, OUTPUT_DIR, **kwargs)

    def test_no_mpi_when_n_processes_zero_or_one(self):
        for n in (0, 1):
            script = self._gen(n_processes=n)
            assert "mpirun" not in script
            assert "mpiexec" not in script

    def test_empty_extra_directives_list_no_crash(self):
        script = self._gen(extra_directives=[])
        assert script.startswith("#!/bin/bash")

    def test_no_module_purge_when_no_modules(self):
        script = self._gen()
        assert "module purge" not in script

    def test_conda_and_modules_both_present(self):
        script = self._gen(modules=["fds/6.9"], conda_env="myenv")
        assert "module load fds/6.9" in script
        assert "conda activate myenv" in script

    def test_nodes_greater_than_n_processes(self):
        # Should not crash; writes directives as given
        script = self._gen(n_processes=2, nodes=8)
        assert "#SBATCH --nodes=8" in script
        assert "#SBATCH --ntasks=2" in script

    def test_custom_mpiexec_used(self):
        script = self._gen(n_processes=4, mpiexec="mpiexec.hydra")
        assert "mpiexec.hydra" in script


# ---------------------------------------------------------------------------
# PbsJobScript
# ---------------------------------------------------------------------------

class TestPbsJobScript:
    def _gen(self, **kwargs):
        return PbsJobScript().generate(FDS_INPUT, OUTPUT_DIR, **kwargs)

    def test_shebang(self):
        assert self._gen().startswith("#!/bin/bash")

    def test_job_name(self):
        script = self._gen(job_name="pbs_job")
        assert "#PBS -N pbs_job" in script

    def test_nodes_ppn(self):
        script = self._gen(nodes=2, ppn=8)
        assert "#PBS -l nodes=2:ppn=8" in script

    def test_walltime(self):
        script = self._gen(time_limit="12:00:00")
        assert "#PBS -l walltime=12:00:00" in script

    def test_queue(self):
        script = self._gen(queue="normal")
        assert "#PBS -q normal" in script

    def test_output_error_paths(self):
        script = self._gen()
        assert ".out" in script
        assert ".err" in script

    def test_modules(self):
        script = self._gen(modules=["fds/6.9"])
        assert "module load fds/6.9" in script

    def test_mpi_when_multiple_processes(self):
        script = self._gen(n_processes=8)
        assert "mpirun" in script or "mpiexec" in script


# ---------------------------------------------------------------------------
# LsfJobScript
# ---------------------------------------------------------------------------

class TestLsfJobScript:
    def _gen(self, **kwargs):
        return LsfJobScript().generate(FDS_INPUT, OUTPUT_DIR, **kwargs)

    def test_shebang(self):
        assert self._gen().startswith("#!/bin/bash")

    def test_job_name(self):
        script = self._gen(job_name="lsf_job")
        assert "#BSUB -J lsf_job" in script

    def test_n_processes(self):
        script = self._gen(n_processes=32)
        assert "#BSUB -n 32" in script

    def test_time_limit(self):
        script = self._gen(time_limit="04:00")
        assert "#BSUB -W 04:00" in script

    def test_queue(self):
        script = self._gen(queue="long")
        assert "#BSUB -q long" in script

    def test_output_error_contain_job_id(self):
        script = self._gen()
        assert "%J" in script or "_J" in script

    def test_mpi_multiple_processes(self):
        script = self._gen(n_processes=4)
        assert "mpirun" in script or "mpiexec" in script


# ---------------------------------------------------------------------------
# HpcManager.generate_script
# ---------------------------------------------------------------------------

class TestGenerateScript:
    def test_slurm_scheduler(self):
        mgr = HpcManager(dry_run=True)
        s = mgr.generate_script("slurm", FDS_INPUT, OUTPUT_DIR)
        assert "#SBATCH" in s

    def test_pbs_scheduler(self):
        mgr = HpcManager(dry_run=True)
        s = mgr.generate_script("pbs", FDS_INPUT, OUTPUT_DIR)
        assert "#PBS" in s

    def test_torque_alias(self):
        mgr = HpcManager(dry_run=True)
        s = mgr.generate_script("torque", FDS_INPUT, OUTPUT_DIR)
        assert "#PBS" in s

    def test_lsf_scheduler(self):
        mgr = HpcManager(dry_run=True)
        s = mgr.generate_script("lsf", FDS_INPUT, OUTPUT_DIR)
        assert "#BSUB" in s

    def test_unknown_scheduler_raises(self):
        mgr = HpcManager(dry_run=True)
        with pytest.raises(ValueError, match="Unknown scheduler"):
            mgr.generate_script("sge", FDS_INPUT, OUTPUT_DIR)


# ---------------------------------------------------------------------------
# HpcManager dry_run — file writing
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_slurm_dry_run_writes_file(self, tmp_path):
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=True)
        result = mgr.submit_slurm(FDS_INPUT, OUTPUT_DIR)
        assert result.script_path is not None
        assert Path(result.script_path).exists()

    def test_pbs_dry_run_writes_file(self, tmp_path):
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=True)
        result = mgr.submit_pbs(FDS_INPUT, OUTPUT_DIR)
        assert Path(result.script_path).exists()

    def test_lsf_dry_run_writes_file(self, tmp_path):
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=True)
        result = mgr.submit_lsf(FDS_INPUT, OUTPUT_DIR)
        assert Path(result.script_path).exists()

    def test_dry_run_result_no_job_id(self, tmp_path):
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=True)
        result = mgr.submit_slurm(FDS_INPUT, OUTPUT_DIR)
        assert result.job_id is None

    def test_dry_run_result_success_false(self, tmp_path):
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=True)
        result = mgr.submit_slurm(FDS_INPUT, OUTPUT_DIR)
        assert not result.success

    def test_dry_run_script_content_correct(self, tmp_path):
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=True)
        result = mgr.submit_slurm(FDS_INPUT, OUTPUT_DIR)
        assert "#SBATCH" in result.script

    def test_script_file_contains_fds_stem(self, tmp_path):
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=True)
        result = mgr.submit_slurm(FDS_INPUT, OUTPUT_DIR)
        content = Path(result.script_path).read_text()
        assert "building" in content

    def test_script_chmod_does_not_raise_on_windows(self, tmp_path):
        # On Windows chmod is a no-op — must not raise
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=True)
        result = mgr.submit_slurm(FDS_INPUT, OUTPUT_DIR)
        assert result is not None


# ---------------------------------------------------------------------------
# HpcSubmitResult repr
# ---------------------------------------------------------------------------

class TestHpcSubmitResult:
    def test_repr(self):
        r = HpcSubmitResult("SLURM", job_id="12345", script="#!/bin/bash")
        assert "SLURM" in repr(r)
        assert "12345" in repr(r)

    def test_success_when_job_id_set(self):
        r = HpcSubmitResult("SLURM", job_id="999", script="")
        assert r.success

    def test_not_success_when_no_job_id(self):
        r = HpcSubmitResult("SLURM", job_id=None, script="")
        assert not r.success

    def test_not_success_when_error(self):
        r = HpcSubmitResult("SLURM", job_id="1", script="", error="timeout")
        assert not r.success


# ---------------------------------------------------------------------------
# Job ID parsing
# ---------------------------------------------------------------------------

class TestParseJobId:
    def test_slurm_format(self):
        out = "Submitted batch job 98765"
        jid = HpcManager._parse_job_id(out, "SLURM")
        assert jid == "98765"

    def test_pbs_format(self):
        out = "12345.pbs-server"
        jid = HpcManager._parse_job_id(out, "PBS")
        assert jid is not None
        assert "12345" in jid

    def test_lsf_format(self):
        out = "Job <54321> is submitted to queue <normal>."
        jid = HpcManager._parse_job_id(out, "LSF")
        assert jid == "54321"

    def test_slurm_no_match_returns_none(self):
        jid = HpcManager._parse_job_id("some other output", "SLURM")
        assert jid is None

    def test_lsf_no_match_returns_none(self):
        jid = HpcManager._parse_job_id("error: bad input", "LSF")
        assert jid is None

    def test_unknown_scheduler_returns_stripped_output(self):
        jid = HpcManager._parse_job_id("  abc123  ", "UNKNOWN")
        assert jid == "abc123"


# ---------------------------------------------------------------------------
# HpcManager when submit command not found
# ---------------------------------------------------------------------------

class TestSubmissionFailure:
    def test_missing_command_returns_error_result(self, tmp_path):
        mgr = HpcManager(script_dir=str(tmp_path), dry_run=False)
        # Use a clearly non-existent binary
        result = mgr._submit(
            "#!/bin/bash\necho test",
            OUTPUT_DIR,
            FDS_INPUT,
            "nonexistent_sbatch_xyz",
            "SLURM",
        )
        assert not result.success
        assert result.error is not None
