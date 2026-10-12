"""Command line: validate, run, convert, new, info, report."""
from __future__ import annotations

import argparse
from pathlib import Path

from .main_common import (
    _print_error,
    _print_ok,
    _print_warn,
)


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate an FDS input file and print the report."""
    from pyfds.api.controller import FdsApi

    api = FdsApi()
    try:
        api.load(args.filepath)
    except Exception as exc:
        _print_error(f"Could not parse {args.filepath}: {exc}")
        return 1

    report = (api.validation.validate_with_plugins()
              if args.plugins else api.validation.validate())

    print(f"\nValidation report for: {args.filepath}")
    print("─" * 60)
    for r in report.errors:
        _print_error(r.message)
    for r in report.warnings:
        _print_warn(r.message)
    if args.verbose:
        for r in report.infos:
            print(f"  ℹ  {r.message}")

    print("─" * 60)
    print(report.summary())

    if args.strict and report.warnings:
        return 2
    return 0 if report.passed else 1


def cmd_run(args: argparse.Namespace) -> int:
    """Run a .pyfds or .fds project through the simulation pipeline."""
    from pyfds.api.controller import FdsApi

    api = FdsApi()
    try:
        api.load(args.filepath)
    except Exception as exc:
        _print_error(f"Could not load {args.filepath}: {exc}")
        return 1

    out_dir = args.output_dir or str(Path(args.filepath).parent / "output")
    result  = api.execution.run(
        output_dir=out_dir,
        validate_first=not args.no_validate,
        num_processes=args.np,
        timeout=args.timeout,
        open_smokeview=args.smokeview,
    )

    print(f"\nSimulation: {api.project.chid}")
    print(f"  Status  : {'✓ COMPLETE' if result.success else '✗ FAILED'}")
    print(f"  RC      : {result.return_code}")
    print(f"  Wall    : {result.wall_time_seconds:.1f}s")
    if result.stats:
        print(f"  T reach : {result.stats.t_reached:.1f}s")
    if result.error:
        _print_error(result.error)

    return 0 if result.success else 1


def cmd_convert(args: argparse.Namespace) -> int:
    """Convert between .fds and .pyfds formats."""
    from pyfds.api.controller import FdsApi

    api = FdsApi()
    try:
        api.load(args.source)
    except Exception as exc:
        _print_error(f"Could not load {args.source}: {exc}")
        return 1

    try:
        api.save(args.dest)
        _print_ok(f"Saved: {args.dest}")
        return 0
    except Exception as exc:
        _print_error(f"Could not save {args.dest}: {exc}")
        return 1


def cmd_new(args: argparse.Namespace) -> int:
    """Create a new project from a preset template."""
    from pyfds.api.controller import FdsApi

    api = FdsApi()

    if args.list:
        presets = api.templates.list_presets()
        print("Available presets:")
        for name in presets:
            print(f"  {name}")
        return 0

    preset = args.preset or "blank"
    try:
        api.new(chid=args.chid or preset)
        kwargs: dict = {}
        if args.t_end is not None:
            kwargs["t_end"] = args.t_end
        api.templates.apply(preset, **kwargs)
    except KeyError as exc:
        _print_error(f"Unknown preset: {exc}")
        return 1

    out_path = args.output or f"{args.chid or preset}.pyfds"
    api.save(out_path)
    _print_ok(f"Project created: {out_path}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """Print metadata about a project file or output directory."""
    path = Path(args.path)

    if path.is_dir():
        # Treat as output directory — build result index
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(path))
        print(idx.summary())
        return 0

    suffix = path.suffix.lower()
    if suffix in (".fds", ".pyfds"):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        try:
            api.load(str(path))
        except Exception as exc:
            _print_error(f"Could not load {path}: {exc}")
            return 1
        print(api.info())
        return 0

    if suffix == ".smv":
        from pyfds.smokeview.smv_parser import SmvParser
        meta = SmvParser().parse(str(path))
        print(f"CHID       : {meta.chid}")
        print(f"Version    : {meta.fds_version}")
        print(f"Grids      : {len(meta.grids)}")
        print(f"Slices     : {len(meta.slices)}  qty={meta.slice_quantities()}")
        print(f"Boundaries : {len(meta.boundaries)}  qty={meta.boundary_quantities()}")
        print(f"Devices    : {len(meta.devices)}")
        return 0

    if suffix == ".q":
        from pyfds.results.plot3d_reader import Plot3DReader
        try:
            result = Plot3DReader.read(str(path))
        except Exception as exc:
            _print_error(f"Could not read {path}: {exc}")
            return 1
        t0, t1 = float(result.times[0]), float(result.times[-1])
        print(f"Plot3D file : {path.name}")
        print(f"  Shape     : {result.shape[0]} × {result.shape[1]} × {result.shape[2]}")
        print(f"  Quantities: {result.quantities}")
        print(f"  Units     : {result.units}")
        print(f"  Frames    : {result.n_frames}")
        print(f"  Time range: {t0:.2f}s → {t1:.2f}s")
        return 0

    if suffix == ".prt5":
        from pyfds.results.particle_reader import ParticleReader
        try:
            result = ParticleReader.read(str(path))
        except Exception as exc:
            _print_error(f"Could not read {path}: {exc}")
            return 1
        print(f"Particle file: {path.name}")
        print(f"  CHID      : {result.chid}")
        print(f"  Classes   : {result.n_classes}")
        for cls in result.classes:
            print(f"    {cls.name:<20}  qty={cls.quantity_names}  frames={cls.n_frames}")
        return 0

    _print_error(f"Unrecognised file type: {suffix}")
    return 1


def cmd_report(args: argparse.Namespace) -> int:
    """Generate a simulation report from an output directory."""
    from pyfds.results.indexer import ResultIndex
    from pyfds.results.report import SimulationReport

    path = Path(args.output_dir)
    if not path.is_dir():
        _print_error(f"Not a directory: {path}")
        return 1

    idx = ResultIndex.build(str(path))
    title = args.title or f"Simulation Report — {idx.chid}"
    rpt = SimulationReport(stats=idx.stats, title=title)

    fmt = args.fmt
    default_ext = "html" if fmt == "html" else "txt"
    out_path = args.output or str(path / f"{idx.chid}_report.{default_ext}")

    try:
        rpt.save(out_path, fmt=fmt)
        _print_ok(f"Report written: {out_path}")
    except Exception as exc:
        _print_error(f"Could not write report: {exc}")
        return 1

    return 0
