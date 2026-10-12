"""Make the small real-FDS run that the results-viewer tests use (tests/fixtures/results_room/).

It runs the real FDS 6.10.1 in ``fds_smv/`` on a two-mesh room fire that writes every kind of output the
viewer shows: 2-D slices, a vector slice, 3-D slices, boundary files, an isosurface, Plot3D, 3-D smoke and
fire, particles, devices and the heat release file. Takes about a minute. Re-run only when the fixture must
change; the output is committed.

    python tools/make_results_fixture.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pyfds.api import FdsApi                                           # noqa: E402

FDS = ROOT / "fds_smv" / "FDS6" / "bin" / "fds.exe"
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("F:/scratch/results_fixture_run")
DEST = ROOT / "tests" / "fixtures" / "results_room"
CHID = "rroom"

#: result files worth keeping (everything else FDS writes is bulk or regenerated)
KEEP = (".smv", ".sf", ".bf", ".iso", ".prt5", ".s3d", ".q", ".out", ".csv", ".fds", ".s3d.sz", ".sf.bnd", ".bf.bnd",
        ".q.bnd", ".prt5.bnd", ".iso.bnd")


def build() -> FdsApi:
    api = FdsApi()
    api.project.chid = CHID
    api.project.title = "Results viewer fixture"
    api.meshes.add_mesh(ijk=(20, 20, 15), xb=(0, 3, 0, 3, 0, 2.25), name="M")
    api.meshes.split("M", "X", 1.5)                                  # two meshes: output is grouped per mesh
    api.surfaces.add_typed("burner", name="BURNER_SURF", heat_release_rate=500.0, tau_q=-3.0, color="ORANGE")
    api.obstructions.add_obstruction([1.2, 1.8, 1.2, 1.8, 0, 0.15], surf_id="BURNER_SURF", name="BURNER")
    api.obstructions.add_obstruction([2.2, 2.6, 0.4, 0.8, 0, 0.45], surf_id="INERT", name="TABLE")
    api.reactions.add_simple_reaction("PROPANE", 46000.0, soot_yield=0.05, name="PROPANE_FIRE")
    api.meshes.open_boundaries()

    api.slices.add_slice("TEMPERATURE", plane="Y", position=1.5, name="T_Y")
    api.slices.add_slice("TEMPERATURE", plane="X", position=1.05, name="T_X")
    api.slices.add_slice("VELOCITY", plane="Y", position=1.5, name="V_Y", vector=True)
    api.slices.add_volume_slice("TEMPERATURE", [0, 3, 0, 3, 0, 2.25], name="T_3D")
    soot = api.slices.add_volume_slice("DENSITY", [0, 3, 0, 3, 0, 2.25], name="SOOT_3D")
    api.slices.set_extra(soot, "SPEC_ID", "'SOOT'")
    api.boundary_files.add_boundary_file("WALL TEMPERATURE", name="BNDF_T") if hasattr(api, "boundary_files") else \
        api.bndfs.add_boundary_file("WALL TEMPERATURE")
    api.isosurfaces.add_isosurface("TEMPERATURE", 100.0, name="ISO_100") if hasattr(api, "isosurfaces") else \
        api.isofs.add_isosurface("TEMPERATURE", 100.0)

    api.species.add_species("WATER VAPOR", formula="H2O", mw=18.015)       # a droplet class needs its species defined
    api.particles.add_particle_class(name="DROPS", spec_id="WATER VAPOR", diameter=1000.0, color="BLUE")
    api.inits.add_init([1.3, 1.7, 1.3, 1.7, 1.2, 1.5], part_id="DROPS", n_particles=150, name="DROP_CLOUD")

    api.props.add_heat_detector("HEAT_DET_PROP", rti=5.0, activation_temperature=74.0)
    api.devices.add_device("LINK TEMPERATURE", [1.5, 1.5, 2.1], name="HEAT_DET", prop_id="HEAT_DET_PROP")
    for z in (0.6, 1.2, 1.8):
        api.devices.add_thermocouple([1.5, 1.5, z], f"TC_{round(z * 100):03d}")

    d = api.project.dump
    d.dt_slcf = d.dt_bndf = d.dt_isof = 0.5
    d.dt_devc = 0.25
    d.dt_pl3d = 3.0
    api.project.dump.fds_extra = {"DT_PART": "0.5"}
    api.config.configure_simulation(t_end=6.0)
    return api


def main() -> int:
    from pyfds.io.fds_writer import FdsWriter
    api = build()
    for r in api.validation.validate().results:
        print(f"  [{r.severity.name}] {r.rule}: {r.message}")
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    result = api.execution.run(str(WORK), fds_binary=str(FDS), timeout=1200, validate_first=False)
    print(result)
    if not result.success:
        print(result.error)
        return 1
    shutil.rmtree(DEST, ignore_errors=True)
    DEST.mkdir(parents=True)
    kept = 0
    for f in sorted(WORK.iterdir()):
        if f.name.endswith(KEEP) and f.stat().st_size < 4_000_000:
            shutil.copy2(f, DEST / f.name)
            kept += 1
    size = sum(f.stat().st_size for f in DEST.iterdir())
    print(f"kept {kept} files, {size / 1e6:.1f} MB in {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
