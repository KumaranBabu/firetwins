"""Command line: batch, render, batch-analyze, diff, compare."""
from __future__ import annotations

import argparse
from pathlib import Path

from .main_common import _print_error, _print_ok


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
