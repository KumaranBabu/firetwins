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
import logging
import sys
from typing import List, Optional

from pyfds.utils.logging_setup import setup_logging

from .main_common import (  # noqa: F401  (re-exported)
    _print_error,
    _print_ok,
    _print_warn,
)
from .main_tools import (  # noqa: F401  (re-exported)
    cmd_autofix,
    cmd_plugins,
    cmd_schema,
)
from .main_batch import (  # noqa: F401  (re-exported)
    cmd_batch,
    cmd_batch_analyze,
    cmd_compare,
    cmd_diff,
    cmd_render,
)
from .main_project import (  # noqa: F401  (re-exported)
    cmd_convert,
    cmd_info,
    cmd_new,
    cmd_report,
    cmd_run,
    cmd_validate,
)

from .main_common import (  # noqa: F401  (re-exported)
    _print_ok,
    _print_warn,
)


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
