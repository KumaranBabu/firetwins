"""
PyFDS Plugin Base Interfaces
=============================
Protocol-based plugin contracts that third-party packages implement to extend
PyFDS without modifying core code.

Plugin types
------------
WriterPlugin        — add custom namelist writers / output formats
ValidationPlugin    — add custom validation rules
ParserPlugin        — add support for non-standard .fds dialects
WorkflowPlugin      — add custom WorkflowStep implementations
PresetPlugin        — add scenario templates / material libraries
ResultPlugin        — add custom result readers or post-processors

Each plugin type is a ``runtime_checkable`` Protocol so plugin authors can
use duck typing (no inheritance required), or inherit from the provided
``PluginBase`` dataclass for metadata registration.

Discovery
---------
Plugins are discovered via:
  1. Directory scan — Python files or packages with ``PYFDS_PLUGIN = True``
  2. ``entry_points`` group ``pyfds.plugins``  (standard Python packaging)
  3. Manual registration via ``PluginRegistry.register()``

Example (writing a custom validation plugin)::

    from pyfds.plugins.base import ValidationPlugin, PluginMetadata
    from pyfds.validation.engine import ValidationResult, Severity

    class MyRule:
        def check(self, project):
            if project.chid == "bad_name":
                return [ValidationResult(Severity.WARNING,
                                         "CHID should not be 'bad_name'")]
            return []

    class MyValidationPlugin:
        metadata = PluginMetadata(
            name="my_validator",
            version="1.0.0",
            author="Example Corp",
            description="Extra project validation rules",
        )
        def validation_rules(self):
            return [MyRule()]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

@dataclass
class PluginMetadata:
    """Self-description record every plugin should provide."""
    name: str
    version: str = "0.0.1"
    author: str = ""
    description: str = ""
    requires: List[str] = field(default_factory=list)    # package dependencies
    tags: List[str] = field(default_factory=list)         # e.g. ["validation", "hvac"]

    def __repr__(self) -> str:
        return f"<PluginMetadata name={self.name!r} v{self.version}>"


# ---------------------------------------------------------------------------
# Base plugin mixin (optional — plugins may use pure duck typing)
# ---------------------------------------------------------------------------

class PluginBase:
    """
    Optional base class for plugins that want automatic metadata registration.

    Subclass this and set ``metadata`` as a class-level attribute.  The
    ``PluginLoader`` will discover it automatically.
    """
    metadata: PluginMetadata = PluginMetadata(name="unnamed")

    def on_load(self, registry: Any) -> None:
        """Called by the loader after this plugin is registered. Override as needed."""

    def on_unload(self, registry: Any) -> None:
        """Called when the plugin is explicitly removed from the registry."""


# ---------------------------------------------------------------------------
# Writer plugin
# ---------------------------------------------------------------------------

@runtime_checkable
class WriterPlugin(Protocol):
    """
    Adds support for writing FDS project data to alternative formats.

    The plugin is consulted after the built-in FdsWriter has run.
    It may write additional output files (e.g., CSV summaries, custom
    namelists, or proprietary formats).

    Required attributes
    -------------------
    name : str
        Unique identifier used to select this writer via CLI/API.
    extensions : list[str]
        File extensions this writer produces, e.g. ``[".csv", ".xml"]``.
    """
    name: str
    extensions: List[str]

    def write(self, project: Any, output_dir: str) -> List[str]:
        """
        Write *project* data to *output_dir*.

        Returns
        -------
        list[str]
            Paths of all files written.
        """
        ...


# ---------------------------------------------------------------------------
# Validation plugin
# ---------------------------------------------------------------------------

@runtime_checkable
class ValidationPlugin(Protocol):
    """
    Contributes additional ``ValidationRule`` objects to the engine.

    The plugin's rules are appended after the built-in rules and run
    as part of the standard ``ValidationEngine.validate()`` call.
    """
    name: str

    def validation_rules(self) -> List[Any]:
        """Return a list of objects implementing the ``ValidationRule`` Protocol."""
        ...


# ---------------------------------------------------------------------------
# Parser plugin
# ---------------------------------------------------------------------------

@runtime_checkable
class ParserPlugin(Protocol):
    """
    Handles parsing of non-standard or proprietary ``.fds`` files.

    If registered, the ``FdsParser`` checks registered ``ParserPlugin``
    implementations before falling back to its own tokenizer.  A plugin
    should return ``None`` if it cannot parse the given file (allowing
    the next plugin or the built-in parser to try).
    """
    name: str
    supported_formats: List[str]     # e.g. ["pyrosim", "firefoam"]

    def can_parse(self, filepath: str) -> bool:
        """Return True if this plugin can parse *filepath*."""
        ...

    def parse(self, filepath: str) -> Any:
        """Parse *filepath* and return an ``FdsProject`` (or raise)."""
        ...


# ---------------------------------------------------------------------------
# Workflow plugin
# ---------------------------------------------------------------------------

@runtime_checkable
class WorkflowPlugin(Protocol):
    """
    Contributes one or more custom ``WorkflowStep`` implementations.

    Registered steps become available by name in ``WorkflowEngine.add_step()``.

    Example::

        class NotifySlackStep:
            name = "notify_slack"
            def execute(self, ctx):
                requests.post(WEBHOOK_URL, json={"text": "Simulation complete!"})
                return ctx
    """
    name: str

    def workflow_steps(self) -> List[Any]:
        """Return a list of ``WorkflowStep``-compatible objects."""
        ...


# ---------------------------------------------------------------------------
# Preset plugin
# ---------------------------------------------------------------------------

@runtime_checkable
class PresetPlugin(Protocol):
    """
    Contributes scenario templates and/or material library entries.

    Templates are registered into ``PresetEngine`` via
    ``PresetEngine.add()``; materials are added to ``MaterialLibrary``.
    """
    name: str

    def scenario_templates(self) -> List[Any]:
        """Return a list of ``ScenarioTemplate`` objects."""
        ...

    def materials(self) -> List[Any]:
        """Return a list of ``MaterialPreset`` objects."""
        ...


# ---------------------------------------------------------------------------
# Meshing plugin
# ---------------------------------------------------------------------------

@runtime_checkable
class MeshingPlugin(Protocol):
    """
    Contributes additional meshing engine implementations.

    Engines registered this way participate in automatic selection
    alongside the built-in engines, respecting the same priority and
    capability rules.

    Example::

        from pyfds.meshing.base import MeshingEngineBase, EngineCapabilities, LicenseType

        class MyCommercialMesher(MeshingEngineBase):
            name         = "acme_mesher"
            display_name = "ACME Pro Mesher 2025"
            priority     = 200          # outranks all built-in engines
            license_type = LicenseType.COMMERCIAL
            capabilities = EngineCapabilities(
                structured_mesh=True,
                volume_mesh=True,
            )

            @classmethod
            def is_available(cls):
                try:
                    import acme_sdk
                    return acme_sdk.is_licensed()
                except ImportError:
                    return False

        class MyMeshingPlugin:
            name = "acme_meshing"
            def meshing_engines(self):
                return [MyCommercialMesher]
    """
    name: str

    def meshing_engines(self) -> List[Any]:
        """Return a list of ``MeshingEngineBase`` subclasses (not instances)."""
        ...


# ---------------------------------------------------------------------------
# Result plugin
# ---------------------------------------------------------------------------

@runtime_checkable
class ResultPlugin(Protocol):
    """
    Adds custom post-processing or result reader capabilities.

    A result plugin is consulted by ``ResultIndex.build()`` when no built-in
    reader can handle a discovered file extension or naming convention.
    """
    name: str
    handled_extensions: List[str]    # e.g. [".hdf5", ".nc"]

    def can_read(self, filepath: str) -> bool:
        """Return True if this plugin can read *filepath*."""
        ...

    def read(self, filepath: str) -> Any:
        """Read *filepath* and return a ``ReaderResult`` (or compatible object)."""
        ...
