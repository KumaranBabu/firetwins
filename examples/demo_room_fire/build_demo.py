"""Demo case, end to end: a furnished-less room with a door and a window, a growing gas burner, a heat
detector and thermocouples. Built entirely through the PyFDS API, validated, saved, run with the real FDS,
and post-processed (slice picture, Smokeview screenshots, device plots, report).

    python examples/demo_room_fire/build_demo.py            # build + run + post-process (a few minutes)
    python examples/demo_room_fire/build_demo.py --no-run   # only build, validate and save

Everything is written next to this script:
    demo_room_fire.pyfds   the editable PyFDS project
    demo_room_fire.fds     the FDS input that was run
    run/                   FDS output (kept so the results can be reopened)
    results/               pictures, device plots, probe table and REPORT.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pyfds.api import FdsApi                                   # noqa: E402
from pyfds.io.serializer import Serializer                     # noqa: E402

FDS_HOME = ROOT / "fds_smv"
FDS = FDS_HOME / "FDS6" / "bin" / "fds.exe"
SMV = FDS_HOME / "SMV6" / "smokeview.exe"
CHID = "demo_room"
T_END = 20.0


def build() -> FdsApi:
    api = FdsApi()
    api.project.chid = CHID
    api.project.title = "Demo: room fire with door, window, heat detector"
    dx = 0.15

    # domain: 6.0 x 4.5 x 3.0 m in 0.15 m cells (room walls sit on cell boundaries)
    api.meshes.add_mesh(ijk=(40, 30, 20), xb=(0, 6.0, 0, 4.5, 0, 3.0), name="DOMAIN")

    # walls from the library: double gypsum board
    api.library.add_to_model("surfaces", "gypsum_wall_25mm")
    room = api.geom.add_room(
        [0.6, 5.4, 0.6, 3.9], height=2.4, wall_thickness=dx, position="inside",
        ceiling_thickness=dx, surf_id="GYPSUM_WALL_25MM", name="ROOM",
        openings=[{"side": "S", "centre": 3.0, "width": 0.9, "height": 2.1},                  # door
                  {"side": "E", "centre": 2.25, "width": 1.2, "height": 1.05, "sill": 0.9}])  # window

    # the fire: 0.6 x 0.6 x 0.15 m gas burner, 500 kW/m2 on all exposed faces, t-squared growth to full size in 15 s
    api.surfaces.add_typed("burner", name="BURNER_SURF", heat_release_rate=500.0, tau_q=-15.0, color="ORANGE")
    api.obstructions.add_obstruction([2.7, 3.3, 2.1, 2.7, 0.0, 0.15], surf_id="BURNER_SURF", name="BURNER")
    api.reactions.add_simple_reaction("PROPANE", 46000.0, soot_yield=0.01, name="PROPANE_FIRE")

    # outside is open
    api.meshes.open_boundaries()

    # instruments: heat detector under the ceiling above the fire, thermocouple tree, HRR comes for free
    det = api.library.add_to_model("heat_detectors", "heat_detector_74C", "HEAT_DET_PROP")
    api.devices.add_device("LINK TEMPERATURE", [3.0, 2.4, 2.35], name="HEAT_DET", prop_id=det.name)
    for z in (0.6, 1.2, 1.8, 2.3):
        api.devices.add_thermocouple([3.0, 2.4, z], f"TC_{round(z * 100):03d}")
    api.devices.add_device("VELOCITY", [3.0, 0.75, 1.0], name="DOOR_VEL")

    # pictures: temperature through the fire (two planes) and visibility at head height
    api.slices.add_slice("TEMPERATURE", plane="Y", position=2.4, name="SLICE_T_Y")
    api.slices.add_slice("TEMPERATURE", plane="X", position=3.0, name="SLICE_T_X")
    api.slices.add_slice("VISIBILITY", plane="Z", position=1.5, name="SLICE_VIS_Z")
    api.config.configure_simulation(t_end=T_END)
    return api


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-run", action="store_true")
    args = ap.parse_args()

    api = build()
    print(f"model: {len(api.obstructions.all())} obstructions, {len(api.holes.all())} holes, "
          f"{api.meshes.project_stats()['total_cells']} cells")

    report = api.validation.validate()
    for r in report.results:
        print(f"  [{r.severity.name}] {r.rule}: {r.message}")
    api.validation.gate()                                          # raises when there are errors

    fds_path = HERE / f"{CHID.replace('demo_room', 'demo_room_fire')}.fds"
    Serializer().save(api.project, str(HERE / "demo_room_fire.pyfds"))
    from pyfds.io.fds_writer import FdsWriter
    FdsWriter().write(api.project, str(fds_path))
    print("saved:", HERE / "demo_room_fire.pyfds", "and", fds_path.name)
    if args.no_run:
        return 0

    run_dir, res_dir = HERE / "run", HERE / "results"
    result = api.execution.run(str(run_dir), fds_binary=str(FDS), timeout=3600)
    print("run:", result)
    if not result.success:
        print(result.error)
        return 1
    postprocess(api, run_dir, res_dir)
    return 0


def postprocess(api: FdsApi, run_dir: Path, res_dir: Path) -> None:
    res_dir.mkdir(exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from pyfds.results.reader import DeviceReader

    # devices
    devc = DeviceReader.read(str(run_dir / f"{CHID}_devc.csv"))
    hrr = DeviceReader.read(str(run_dir / f"{CHID}_hrr.csv"))
    fig = Figure(figsize=(9, 6))
    ax = fig.subplots(2, 1, sharex=True)
    ax[0].plot(hrr["Time"].data, hrr["HRR"].data, color="tab:red")
    ax[0].set_ylabel("HRR (kW)")
    ax[0].grid(alpha=.3)
    for name, r in devc.items():
        if name.startswith("TC_"):
            ax[1].plot(r.times, r.data, label=name)
    ax[1].set_ylabel("gas temperature (C)")
    ax[1].set_xlabel("time (s)")
    ax[1].legend(ncol=4, fontsize=8)
    ax[1].grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(res_dir / "hrr_and_thermocouples.png", dpi=110)

    # results scene: slices, probe table, flat pictures
    api.scene.open_results(str(run_dir))
    layers = api.scene.add_slices()
    pb = api.scene.playback
    pb.seek_time(T_END)
    probes = {}
    for label, pt in {"above burner 1.2 m": (3.0, 2.4, 1.2), "under ceiling": (3.0, 2.4, 2.3),
                      "door opening": (3.0, 0.75, 1.0), "far corner": (1.0, 1.0, 1.0)}.items():
        probes[label] = [{"layer": h["layer"], "quantity": h["quantity"], "value": round(h["value"], 1),
                          "units": h["units"]} for h in api.scene.probe(pt)]
    (res_dir / "probes_at_end.json").write_text(json.dumps(probes, indent=2))
    temp_layers = [l for l in layers if l.quantity == "TEMPERATURE"]
    for l in temp_layers:
        api.slice_view.render(l.result, str(res_dir / f"{l.name}.png"), -1, "DOMAIN")

    # real Smokeview screenshots
    api.config.set("smv_binary", str(SMV))
    shots = api.smokeview.render_screenshots(str(run_dir / f"{CHID}.smv"), [5.0, 10.0, 20.0], "TEMPERATURE",
                                             str(res_dir / "smokeview"))

    det_t = None
    if "HEAT_DET" in devc:
        d = devc["HEAT_DET"]
        det_t = d.times[(d.data >= 74.0).argmax()] if (d.data >= 74.0).any() else None
    peak_hrr = float(hrr["HRR"].data.max())
    lines = [
        "# Demo case: room fire", "",
        "Built, validated, run and post-processed by `build_demo.py` (all through the PyFDS API, real FDS 6.10.1).", "",
        "| item | value |", "|---|---|",
        f"| domain | 6.0 x 4.5 x 3.0 m, 0.15 m cells, {api.meshes.project_stats()['total_cells']} cells |",
        "| room | 4.8 x 3.3 x 2.4 m, 0.15 m gypsum walls and ceiling, door 0.9 x 2.1 m, window 1.2 x 1.05 m |",
        "| fire | 0.6 x 0.6 m propane burner, 500 kW/m2 on top and sides (0.72 m2, about 360 kW at full size), t-squared growth over 15 s |",
        f"| simulated time | {T_END:g} s |", f"| peak HRR | {peak_hrr:.0f} kW |",
        f"| heat detector (74 C) reached at | {'%.1f s' % det_t if det_t is not None else 'not reached'} |", "",
        "## Pictures", "",
        "- `hrr_and_thermocouples.png` - heat release rate and thermocouple tree",
        *[f"- `{l.name}.png` - temperature slice at the end of the run" for l in temp_layers],
        *[f"- `smokeview/{Path(p).name}` - real Smokeview screenshot" for p in shots], "",
        "## Probe values at the end of the run", "",
        "```json", json.dumps(probes, indent=2), "```", "",
        "## Reopen", "",
        "```python", "from pyfds.api import FdsApi", "from pyfds.io.serializer import Serializer",
        "api = FdsApi(Serializer().load('examples/demo_room_fire/demo_room_fire.pyfds'))",
        "api.scene.open_results('examples/demo_room_fire/run')", "```", ""]
    (res_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("report:", res_dir / "REPORT.md")


if __name__ == "__main__":
    raise SystemExit(main())
