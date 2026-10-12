"""
PyFDS Command-Line Interface
=============================
Entry point for the ``pyfds`` CLI tool.

Sub-commands
------------
validate    — validate an FDS input file
autofix     — validate + apply auto-fixes, then (optionally) save the corrected file
run         — write + run a .pyfds project through FDS
convert     — convert between .fds and .pyfds formats
batch       — run a parametric batch study from a config file
render      — headless Smokeview screenshot / movie rendering
new         — create a blank .pyfds project from a preset
info        — print metadata about a project, result directory, or binary file
report      — generate a text or HTML simulation report from an output directory
plugins     — list or load plugins
schema      — print property schema metadata for FDS entity types

Usage examples::

    pyfds validate case.fds
    pyfds validate case.fds --strict

    pyfds run case.pyfds --output-dir runs/case_01 --np 4
    pyfds run case.fds    --output-dir runs/case_01

    pyfds convert case.fds case.pyfds
    pyfds convert case.pyfds case.fds

    pyfds batch study.json --output-root batch_results/ --workers 4

    pyfds render case.smv --times 30 60 90 --quantity TEMPERATURE
    pyfds render case.smv --movie case_movie.avi --fps 10

    pyfds new room_fire --chid my_room --t-end 120 --output my_room.pyfds
    pyfds new --list

    pyfds info case.fds
    pyfds info runs/case_01/
    pyfds info case_01.q
    pyfds info case_01.prt5

    pyfds report runs/case_01/ -o report.html --fmt html
    pyfds report runs/case_01/ --title "Room Fire Study"

    pyfds plugins --list
    pyfds plugins --load /path/to/plugin_dir

    pyfds autofix case.fds
    pyfds autofix case.fds --output fixed.fds
    pyfds autofix case.pyfds --in-place

    pyfds schema
    pyfds schema Mesh
    pyfds schema --json Obstruction
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from pyfds.utils.logging_setup import setup_logging


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_error(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def _print_ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _print_warn(msg: str) -> None:
    print(f"  ⚠  {msg}")


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

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


def cmd_batch(args: argparse.Namespace) -> int:
    """Run a parametric batch study defined in a JSON config file."""
    from pyfds.execution.batch_config import BatchStudyConfig, BatchConfigError

    try:
        cfg = BatchStudyConfig.from_file(args.config)
    except BatchConfigError as exc:
        _print_error(str(exc))
        return 1
    except Exception as exc:
        _print_error(f"Could not load batch config {args.config}: {exc}")
        return 1

    # CLI flags override config values
    if args.output_root:
        cfg.output_root = args.output_root
    if args.workers:
        cfg.max_workers = args.workers
    if args.dry_run:
        cfg.run_simulations = False

    print(f"\nBatch study : {cfg.name}")
    print(f"Variants    : {cfg.n_variants}")
    print(f"Workers     : {cfg.max_workers}")
    print(f"Output root : {cfg.output_root}")
    print(f"Dry run     : {not cfg.run_simulations}")
    print("─" * 60)

    study, executor = cfg.build()
    report = executor.run(study)

    print(f"\n{report.summary()}")
    for vr in report.variant_results:
        status = vr.get("status", "?")
        name   = vr.get("name", "?")
        wt     = vr.get("wall_time")
        wt_str = f"{wt:.1f}s" if wt else "—"
        print(f"  {status:12s}  {name}  ({wt_str})")

    return 0 if report.failed == 0 else 1


def cmd_render(args: argparse.Namespace) -> int:
    """Headless Smokeview rendering."""
    from pyfds.api.controller import FdsApi

    api     = FdsApi()
    smv_mgr = api.smokeview

    smv_path = args.smv_file
    if not Path(smv_path).exists():
        _print_error(f"SMV file not found: {smv_path}")
        return 1

    if args.movie:
        builder = smv_mgr.build_script()
        if args.times:
            t_start = args.times[0]
            t_end   = args.times[-1]
        else:
            t_start = t_end = None
        builder.load_slice(quantity=args.quantity)
        builder.render_movie(args.movie, fps=args.fps,
                             start_time=t_start, end_time=t_end)
        from pyfds.smokeview.runner import SmokeviewRunner
        rc = SmokeviewRunner().render(smv_path, script_content=builder.build(),
                                      output_dir=args.output_dir)
        return 0 if rc == 0 else 1

    times = args.times or []
    paths = smv_mgr.render_screenshots(
        smv_path, times,
        quantity=args.quantity,
        output_dir=args.output_dir,
    )
    for p in paths:
        _print_ok(p)
    return 0


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


def cmd_plugins(args: argparse.Namespace) -> int:
    """Manage plugins."""
    from pyfds.api.controller import FdsApi

    api = FdsApi()

    if args.load:
        n = api.plugins.load_directory(args.load)
        _print_ok(f"Loaded {n} plugins from {args.load}")

    if args.entry_points:
        n = api.plugins.load_entry_points()
        _print_ok(f"Loaded {n} entry-point plugins")

    plugins = api.plugins.all_plugins()
    if plugins:
        print("\nRegistered plugins:")
        for p in plugins:
            meta = getattr(p, "metadata", None)
            name = meta.name if meta else getattr(p, "name", "?")
            ver  = meta.version if meta else ""
            desc = meta.description if meta else ""
            print(f"  {name:<24}  v{ver:<8}  {desc}")
    else:
        print("No plugins registered.")
    return 0


def cmd_autofix(args: argparse.Namespace) -> int:
    """Validate a project and apply all available auto-fixes."""
    from pyfds.api.controller import FdsApi

    api = FdsApi()
    try:
        api.load(args.filepath)
    except Exception as exc:
        _print_error(f"Could not load {args.filepath}: {exc}")
        return 1

    report = api.validation.auto_fix()

    fixed = sum(1 for r in report.results if r.fix is not None)
    print(f"\nAutofix report for: {args.filepath}")
    print("─" * 60)
    for r in report.errors:
        marker = "✓ fixed" if r.fix is not None else "✗ no fix"
        print(f"  {marker}  [ERROR] {r.message}")
    for r in report.warnings:
        marker = "✓ fixed" if r.fix is not None else "⚠ no fix"
        print(f"  {marker}  {r.message}")
    print("─" * 60)
    print(f"Fixes applied : {fixed}")
    print(report.summary())

    if args.in_place:
        dest = args.filepath
    elif args.output:
        dest = args.output
    else:
        dest = None

    if dest:
        try:
            api.save(dest)
            _print_ok(f"Saved fixed project: {dest}")
        except Exception as exc:
            _print_error(f"Could not save {dest}: {exc}")
            return 1

    return 0 if report.passed else 1


def cmd_schema(args: argparse.Namespace) -> int:
    """Print property schema metadata for FDS entity types."""
    from pyfds.api.controller import FdsApi

    api = FdsApi()
    registry = api.schema

    if args.entity:
        schema = registry.get(args.entity)
        if schema is None:
            _print_error(f"No schema registered for {args.entity!r}")
            print(f"Available: {', '.join(sorted(registry.entity_names))}")
            return 1

        if args.json:
            print(json.dumps(schema.to_dict(), indent=2))
            return 0

        print(f"\nSchema: {schema.display_name}  ({schema.fds_namelist})")
        print(f"Category   : {schema.category}")
        if schema.description:
            print(f"Description: {schema.description}")
        print("─" * 60)
        cats: dict = {}
        for prop in schema.properties:
            cats.setdefault(prop.category or "General", []).append(prop)
        for cat, props in cats.items():
            print(f"\n  [{cat}]")
            for p in props:
                req  = "*" if p.required else " "
                unit = f"  [{p.units}]" if p.units else ""
                print(f"  {req} {p.display_name:<28} {p.field_type.name:<12}{unit}")
        return 0

    # List all schemas
    names = sorted(registry.entity_names)
    if args.json:
        all_data = {n: registry.get(n).to_dict() for n in names}
        print(json.dumps(all_data, indent=2))
        return 0

    print("\nRegistered entity schemas:")
    for name in names:
        s = registry.get(name)
        n_props = len(s.properties)
        print(f"  {name:<24} {s.fds_namelist:<8}  {n_props} properties  — {s.description or ''}")
    return 0


def cmd_batch_analyze(args: argparse.Namespace) -> int:
    """Post-process a completed parametric study and export statistics."""
    from pyfds.results.batch_analysis import BatchResultAnalyzer

    analyzer = BatchResultAnalyzer(
        args.output_root,
        study_name=args.study_name,
        outlier_sigma=args.sigma,
    )
    try:
        report = analyzer.analyze()
    except Exception as exc:
        _print_error(f"Analysis failed: {exc}")
        return 1

    print(report.summary())

    if args.csv:
        report.to_csv(args.csv)
        _print_ok(f"CSV written: {args.csv}")
    if args.html:
        report.to_html(args.html, title=args.title or "Batch Analysis Report")
        _print_ok(f"HTML written: {args.html}")
    if args.json:
        report.to_json(args.json)
        _print_ok(f"JSON written: {args.json}")

    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Structural diff between two FDS / .pyfds project files."""
    from pyfds.api.controller import FdsApi

    def _load(path: str) -> object:
        a = FdsApi()
        try:
            a.load(path)
        except Exception as exc:
            _print_error(f"Could not load {path}: {exc}")
            raise SystemExit(1)
        return a.project

    p1 = _load(args.file1)
    p2 = _load(args.file2)

    from pyfds.domain.model import FdsProject
    _TYPE_MAP = FdsProject._TYPE_MAP
    col_names = sorted({v for v in _TYPE_MAP.values()})

    added: list = []
    removed: list = []
    changed: list = []

    for col in col_names:
        c1 = {getattr(e, "name", str(i)): e
              for i, e in enumerate(getattr(p1, col, []))}
        c2 = {getattr(e, "name", str(i)): e
              for i, e in enumerate(getattr(p2, col, []))}
        for n in sorted(set(c2) - set(c1)):
            added.append((col, n))
        for n in sorted(set(c1) - set(c2)):
            removed.append((col, n))
        for n in sorted(set(c1) & set(c2)):
            d1 = c1[n].model_dump()
            d2 = c2[n].model_dump()
            diffs = {k for k in set(d1) | set(d2)
                     if d1.get(k) != d2.get(k) and k != "_uid"}
            if diffs:
                changed.append((col, n, sorted(diffs)))

    # Parameter blocks
    param_blocks = [("params", p1.params, p2.params),
                    ("misc",   p1.misc,   p2.misc),
                    ("dump",   p1.dump,   p2.dump),
                    ("pres",   p1.pres,   p2.pres),
                    ("radi",   p1.radi,   p2.radi)]
    for bname, b1, b2 in param_blocks:
        d1, d2 = b1.model_dump(), b2.model_dump()
        diff_keys = [k for k in d1 if d1[k] != d2.get(k)]
        for k in diff_keys:
            changed.append((bname, k, [f"{d1[k]} → {d2.get(k)}"]))

    if not added and not removed and not changed:
        print("Files are identical (no structural differences).")
        return 0

    print(f"\nDiff: {args.file1}  vs  {args.file2}")
    print("─" * 60)
    for col, name in added:
        print(f"  +  [{col}] {name}")
    for col, name in removed:
        print(f"  -  [{col}] {name}")
    for col, name, fields in changed:
        fstr = ", ".join(fields) if not any("→" in f for f in fields) else "; ".join(fields)
        print(f"  ~  [{col}] {name}  — fields: {fstr}")
    print("─" * 60)
    print(f"  {len(added)} added, {len(removed)} removed, {len(changed)} modified")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare simulation result metrics between two output directories."""
    from pyfds.results.reader import DeviceReader
    from pathlib import Path

    def _read_csv(d: str):
        p = Path(d)
        csvs = list(p.glob("*.csv"))
        if not csvs:
            _print_error(f"No CSV result files found in {d}")
            return None
        return DeviceReader().read(str(csvs[0]))

    r1 = _read_csv(args.dir1)
    r2 = _read_csv(args.dir2)
    if r1 is None or r2 is None:
        return 1

    channels1 = set(r1.channel_names)
    channels2 = set(r2.channel_names)

    print(f"\nResult comparison: {args.dir1}  vs  {args.dir2}")
    print("─" * 60)
    only1 = sorted(channels1 - channels2)
    only2 = sorted(channels2 - channels1)
    common = sorted(channels1 & channels2)

    if only1:
        print(f"\nOnly in {args.dir1}:")
        for c in only1:
            print(f"  - {c}")
    if only2:
        print(f"\nOnly in {args.dir2}:")
        for c in only2:
            print(f"  + {c}")

    if common:
        print(f"\nCommon channels ({len(common)}) — peak value comparison:")
        print(f"  {'Channel':<35} {'Peak A':>12}  {'Peak B':>12}  {'Delta %':>9}")
        print("  " + "-" * 72)
        for c in common:
            try:
                v1 = r1.peak(c)
                v2 = r2.peak(c)
                denom = max(abs(v1), abs(v2), 1e-12)
                delta_pct = (v2 - v1) / denom * 100.0
                flag = "  *" if abs(delta_pct) > (args.threshold or 5.0) else ""
                print(f"  {c:<35} {v1:>12.3f}  {v2:>12.3f}  {delta_pct:>+8.1f}%{flag}")
            except Exception:
                print(f"  {c:<35}  (comparison error)")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfds",
        description="PyFDS — Python toolkit for NIST FDS and Smokeview",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log level (default: WARNING)",
    )
    parser.add_argument(
        "--log-file", default=None,
        help="Write logs to this file (rotating)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── validate ────────────────────────────────────────────────────────────
    p_val = sub.add_parser("validate", help="Validate an FDS input file")
    p_val.add_argument("filepath", help="Path to .fds or .pyfds file")
    p_val.add_argument("--strict", action="store_true",
                       help="Return exit code 2 if warnings are present")
    p_val.add_argument("--plugins", action="store_true",
                       help="Include rules from registered plugins")
    p_val.add_argument("-v", "--verbose", action="store_true",
                       help="Show informational messages too")
    p_val.set_defaults(func=cmd_validate)

    # ── run ─────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Run a project through FDS")
    p_run.add_argument("filepath", help="Path to .fds or .pyfds file")
    p_run.add_argument("-o", "--output-dir", default=None,
                       help="Output directory for FDS results")
    p_run.add_argument("--np", type=int, default=1,
                       help="Number of MPI processes (default: 1)")
    p_run.add_argument("--timeout", type=float, default=None,
                       help="Max wall-clock seconds before FDS is killed")
    p_run.add_argument("--no-validate", action="store_true",
                       help="Skip pre-run validation")
    p_run.add_argument("--smokeview", action="store_true",
                       help="Launch Smokeview after a successful run")
    p_run.set_defaults(func=cmd_run)

    # ── convert ─────────────────────────────────────────────────────────────
    p_conv = sub.add_parser("convert", help="Convert between .fds and .pyfds")
    p_conv.add_argument("source", help="Source file (.fds or .pyfds)")
    p_conv.add_argument("dest",   help="Destination file (.fds or .pyfds)")
    p_conv.set_defaults(func=cmd_convert)

    # ── batch ────────────────────────────────────────────────────────────────
    p_batch = sub.add_parser("batch", help="Run a parametric batch study")
    p_batch.add_argument("config", help="JSON batch config file")
    p_batch.add_argument("--output-root", default=None,
                         help="Root directory for batch variant outputs")
    p_batch.add_argument("--workers", type=int, default=None,
                         help="Max concurrent FDS processes")
    p_batch.add_argument("--dry-run", action="store_true",
                         help="Generate variant .fds files without running FDS")
    p_batch.set_defaults(func=cmd_batch)

    # ── render ───────────────────────────────────────────────────────────────
    p_rend = sub.add_parser("render", help="Headless Smokeview rendering")
    p_rend.add_argument("smv_file", help="Path to .smv file")
    p_rend.add_argument("--times", type=float, nargs="+",
                        help="Simulation times for screenshots")
    p_rend.add_argument("--quantity", default="TEMPERATURE",
                        help="Slice quantity to render (default: TEMPERATURE)")
    p_rend.add_argument("--movie", default=None,
                        help="Render a movie to this path (.avi / .mp4)")
    p_rend.add_argument("--fps", type=int, default=10,
                        help="Movie frame rate (default: 10)")
    p_rend.add_argument("--output-dir", default=None,
                        help="Directory for rendered images")
    p_rend.set_defaults(func=cmd_render)

    # ── new ──────────────────────────────────────────────────────────────────
    p_new = sub.add_parser("new", help="Create a new project from a preset")
    p_new.add_argument("preset", nargs="?", default=None,
                       help="Preset name (e.g. room_fire, pool_fire)")
    p_new.add_argument("--list", action="store_true",
                       help="List available presets and exit")
    p_new.add_argument("--chid", default=None,
                       help="Set the case CHID")
    p_new.add_argument("--t-end", type=float, default=None,
                       help="Override simulation end time (seconds)")
    p_new.add_argument("-o", "--output", default=None,
                       help="Output file path (default: <preset>.pyfds)")
    p_new.set_defaults(func=cmd_new)

    # ── info ─────────────────────────────────────────────────────────────────
    p_info = sub.add_parser("info", help="Print metadata about a file or directory")
    p_info.add_argument("path",
                        help="Path to .fds, .pyfds, .smv, or output directory")
    p_info.set_defaults(func=cmd_info)

    # ── report ───────────────────────────────────────────────────────────────
    p_rep = sub.add_parser("report", help="Generate a simulation report from an output directory")
    p_rep.add_argument("output_dir", help="FDS output directory to analyse")
    p_rep.add_argument("-o", "--output", default=None,
                       help="Report output path (default: <chid>_report.<ext>)")
    p_rep.add_argument("--fmt", choices=["text", "html"], default="text",
                       help="Report format (default: text)")
    p_rep.add_argument("--title", default=None,
                       help="Report title (default: auto from CHID)")
    p_rep.set_defaults(func=cmd_report)

    # ── plugins ──────────────────────────────────────────────────────────────
    p_plug = sub.add_parser("plugins", help="List or load plugins")
    p_plug.add_argument("--list", action="store_true",
                        help="List all registered plugins (default)")
    p_plug.add_argument("--load", default=None, metavar="DIR",
                        help="Load plugins from a directory")
    p_plug.add_argument("--entry-points", action="store_true",
                        help="Load all entry-point plugins")
    p_plug.set_defaults(func=cmd_plugins)

    # ── autofix ──────────────────────────────────────────────────────────────
    p_fix = sub.add_parser("autofix",
                           help="Validate and apply auto-fixes to a project file")
    p_fix.add_argument("filepath", help="Path to .fds or .pyfds file")
    p_fix.add_argument("-o", "--output", default=None,
                       help="Save the fixed project to this path")
    p_fix.add_argument("--in-place", action="store_true",
                       help="Overwrite the source file with the fixed version")
    p_fix.set_defaults(func=cmd_autofix)

    # ── schema ───────────────────────────────────────────────────────────────
    p_sch = sub.add_parser("schema",
                           help="Print property schema metadata for FDS entity types")
    p_sch.add_argument("entity", nargs="?", default=None,
                       help="Entity class name (e.g. Mesh, Obstruction). "
                            "Omit to list all schemas.")
    p_sch.add_argument("--json", action="store_true",
                       help="Output as JSON")
    p_sch.set_defaults(func=cmd_schema)

    # ── batch-analyze ────────────────────────────────────────────────────────
    p_ba = sub.add_parser("batch-analyze",
                          help="Post-process a completed parametric study")
    p_ba.add_argument("output_root",
                      help="Root directory that contains variant sub-directories")
    p_ba.add_argument("--study-name", default=None,
                      help="Sub-directory name for the study (optional)")
    p_ba.add_argument("--sigma", type=float, default=2.0,
                      help="Outlier detection threshold in standard deviations (default: 2.0)")
    p_ba.add_argument("--csv", default=None, metavar="PATH",
                      help="Write summary statistics to this CSV file")
    p_ba.add_argument("--html", default=None, metavar="PATH",
                      help="Write styled HTML report to this file")
    p_ba.add_argument("--json", default=None, metavar="PATH",
                      help="Write full JSON report to this file")
    p_ba.add_argument("--title", default=None,
                      help="Report title for HTML output")
    p_ba.set_defaults(func=cmd_batch_analyze)

    # ── diff ─────────────────────────────────────────────────────────────────
    p_diff = sub.add_parser("diff",
                            help="Structural diff between two FDS project files")
    p_diff.add_argument("file1", help="First .fds or .pyfds file (baseline)")
    p_diff.add_argument("file2", help="Second .fds or .pyfds file (modified)")
    p_diff.set_defaults(func=cmd_diff)

    # ── compare ──────────────────────────────────────────────────────────────
    p_cmp = sub.add_parser("compare",
                           help="Compare simulation result metrics between two output directories")
    p_cmp.add_argument("dir1", help="Baseline results directory")
    p_cmp.add_argument("dir2", help="Modified results directory")
    p_cmp.add_argument("--threshold", type=float, default=5.0,
                       help="Flag channels with delta > this %% (default: 5.0)")
    p_cmp.set_defaults(func=cmd_compare)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)

    setup_logging(level=args.log_level, log_file=getattr(args, "log_file", None))

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        _print_error(str(exc))
        if logging.getLogger("pyfds").isEnabledFor(logging.DEBUG):
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
