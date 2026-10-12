"""Command line: plugins, autofix, schema."""
from __future__ import annotations

import argparse
import json

from .main_common import _print_error, _print_ok


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
