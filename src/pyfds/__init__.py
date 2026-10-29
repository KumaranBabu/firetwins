"""
PyFDS v0.3.0
============
Python backend for NIST Fire Dynamics Simulator (FDS) and Smokeview (SMV).

Quick start
-----------
>>> from pyfds import FdsApi
>>> api = FdsApi()
>>> api.templates.apply("room_fire")
>>> result = api.execution.run(output_dir="runs/room_01")

Package layout
--------------
pyfds.api            — FdsApi high-level facade (primary entry point)
pyfds.core           — EventBus, exceptions, state, session, config
pyfds.domain         — FDS entity models, geometry, materials, presets
pyfds.io             — Parser, writer, JSON serializer
pyfds.validation     — Pluggable validation engine + built-in rules
pyfds.execution      — Job, queue, runner, batch/parametric studies
pyfds.results        — Device/log/slice/boundary readers + index
pyfds.smokeview      — Launcher, SMV parser, binary extractor, scripting
pyfds.automation     — Orchestrator, workflow engine, command pipeline
pyfds.plugins        — Plugin loader, base protocols, registry
pyfds.cli            — Command-line interface (``pyfds`` command)
pyfds.utils          — Formatting helpers, logging setup

Backward compatibility
----------------------
All names that existed in the flat v0.2.0 API are re-exported here so
that existing code continues to work without modification.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# New public API (v0.3.0)
# ---------------------------------------------------------------------------
from pyfds.api.controller import FdsApi                          # primary facade

# Core layer
from pyfds.core.events     import EventBus, EventType, get_global_bus
from pyfds.core.exceptions import (
    FdsError, FdsValidationError, FdsExecutionError, FdsParseError,
    FdsSerializationError, FdsPluginError, FdsConfigError,
    FdsJobError, FdsNotFoundError, FdsTimeoutError, FdsBinaryError,
)
from pyfds.core.config     import FdsConfig, get_config
from pyfds.api.session     import Session, SessionManager
from pyfds.core.state      import StateSnapshot, StateManager, build_snapshot
from pyfds.core.selection  import SelectionManager, SelectionMode, SelectionSnapshot
from pyfds.core.viewport   import (
    ViewportCamera, ViewportState, ViewportController,
    TransformMode, CameraPreset, ProjectionMode, VisibilityFlags, SnapSettings,
)

# Domain layer
from pyfds.domain.model    import (
    FdsProject,
    Mesh, Obstruction, Surface, Vent, Device, Material, Reaction,
    Ramp, Control, Prop, Particle, Species,
    HvacNode, HvacDuct, Fan, Damper,
    Zone, Prof,
    Slice, Smoke3D, BoundaryFile, IsoSurface,
    SimulationParams, DumpParams, MiscParams, PresParams, RadiParams,
    # Phase 1 additions
    Layer, MaterialReaction, Geom, Plot3D, MeshTransform,
    Hole, Mult, Init, Hvac,
    # Gap-fill additions
    WindProfile, Move, HvacFilter, HvacLeakage,
)
# Canonical v0.3 aliases for the above (normalised naming)
Spec          = Species
HvacFan       = Fan
HvacDamper    = Damper
BoundaryOutput = BoundaryFile
Isosurface    = IsoSurface
TimeParams    = SimulationParams
PressParams   = PresParams
from pyfds.domain.geometry  import BoundingBox, GeometryHelper
from pyfds.domain.materials import MaterialLibrary, MaterialPreset
from pyfds.domain.presets   import PresetEngine, ScenarioTemplate, apply_preset, list_presets
from pyfds.domain.schema    import (
    PropertyDescriptor, FieldType, EntitySchema, SchemaRegistry, get_schema_registry,
)
from pyfds.domain.factory   import EntityFactory
from pyfds.domain.egress    import EgressScenario, ExitZone, OccupantGroup, TenabilityLimit

# IO layer
from pyfds.io.fds_parser    import FdsParser
from pyfds.io.fds_writer    import FdsWriter
from pyfds.io.serializer    import Serializer

# Validation
from pyfds.validation.engine import ValidationEngine, ValidationReport, ValidationResult, Severity

# Execution
from pyfds.execution.job        import Job, JobStatus
from pyfds.execution.runner     import SimulationRunner
from pyfds.execution.queue      import JobQueue
from pyfds.execution.batch      import ParametricStudy, BatchExecutor, BatchReport
from pyfds.execution.batch_config import BatchStudyConfig, BatchConfigError, AxisConfig

# Results — core readers and indexer
from pyfds.results.reader    import DeviceReader, LogParser, SliceReader, BoundaryReader, SimulationStats
from pyfds.results.indexer   import ResultIndex, SliceIndex, BoundaryIndex
# Results — Phase 2/3: binary readers, plotters, report
from pyfds.results.plot3d_reader import Plot3DReader, Plot3DResult
from pyfds.results.particle_reader import (
    ParticleReader, ParticleResult, ParticleClass, ParticleFrame,
)
from pyfds.results.plotters  import (
    plot_device_timeseries, plot_hrr, plot_slice_contour,
    plot_multi_quantity, plot_particle_positions,
)
from pyfds.results.report      import SimulationReport, ReportSection
from pyfds.results.comparator  import SimulationComparator, ComparisonReport, ChannelComparison
from pyfds.results.batch_analysis import (
    BatchResultAnalyzer, BatchAnalysisReport, VariantSummary, ChannelStats,
)

# Smokeview
from pyfds.smokeview.runner    import SmokeviewRunner
from pyfds.smokeview.smv_parser import (
    SmvParser, SmvMetadata, SmvGrid, SmvSlice, SmvBoundary,
    SmvIsosurface, SmvDevice, SmvPlot3D, SmvSmoke3D, SmvParticle,
    SmvViewpoint, SmvSurface,
)
from pyfds.smokeview.binary    import SmvBinaryExtractor
from pyfds.smokeview.scripting import SsfScriptBuilder
from pyfds.smokeview.ini_writer import (
    SmvIniConfig, SmvIniWriter, SmvIniParser,
    SmvColorbarConfig, SmvSurfaceColor, SmvIniUnsupported,
)

# Automation
from pyfds.automation.orchestrator import ScenarioOrchestrator, OrchestratorResult
from pyfds.automation.workflow     import (
    WorkflowEngine, WorkflowContext, WorkflowStep,
    ValidateStep, WriteStep, RunStep, RenderStep, CollectResultsStep,
)
from pyfds.automation.commands     import (
    Command, CommandPipeline, CommandResult,
    AddEntityCommand, RemoveEntityCommand, ModifyPropertyCommand,
    GroupCommand, DuplicateEntityCommand, SetHrrCommand, ScaleCommand,
)

# Meshing
from pyfds.meshing import (
    MeshingManager, EngineRegistry, get_engine_registry,
    MeshingEngineBase, MeshingEngine,
    EngineCapabilities, EngineStatus, LicenseType, ElementType,
    MeshResult, GeometryResult, FdsStructuredMesh, MeshData,
    StructuredMeshRequest, SurfaceMeshRequest, VolumeMeshRequest,
    GeometryImportRequest,
    BoundingBoxGeometry, SurfaceMeshGeometry, FileGeometry,
    BuiltinStructuredEngine, GmshEngine, TetGenEngine, NetgenEngine,
)

# Plugins
from pyfds.plugins.base   import PluginBase, PluginMetadata
from pyfds.plugins.loader import PluginLoader, PluginRegistry, get_registry

# Utils
from pyfds.utils.formatting    import fmt_xb, fmt_ijk, fmt_xyz, fmt_float, fds_bool, fds_str
from pyfds.utils.logging_setup import setup_logging, get_logger

# Fire Engineering Calculators
from pyfds.engineering import (
    GrowthRate, FireGrowthResult,
    t_squared_hrr, time_to_hrr, fire_area, equivalent_diameter,
    characterise_fire, generate_hrr_curve, hrr_curve_for_fds_ramp,
    CeilingJetResult, HeskestadResult, SprinklerResponseResult,
    alpert_ceiling_jet, alpert_detector_r_max,
    heskestad_flame_height, heskestad_virtual_origin, heskestad_plume,
    sprinkler_rti,
    MeshAdvice, MpiDecompositionAdvice,
    d_star, q_star, recommend_cell_size,
    poisson_ijk_for_domain, mpi_split_advice,
    CriticalVelocityResult, BackLayeringResult, SpillPlumeResult,
    critical_velocity, back_layering_length, atrium_plume_mass_flow,
    smoke_filling_time,
    ZoneModelResult, DetectorResponseResult,
    two_layer_zone_model, detector_response_time,
)

# Reaction library
from pyfds.domain.reactions import (
    FUEL_LIBRARY, list_fuels, get_fuel, make_reaction,
)

# Quantity library
from pyfds.domain.quantities import (
    FdsQuantity, QUANTITY_DB,
    list_quantities, get_quantity, quantities_for_context, validate_quantity,
    CONTEXT_DEVC, CONTEXT_SLCF, CONTEXT_BNDF, CONTEXT_ISOF,
    CONTEXT_PL3D, CONTEXT_PROF, CONTEXT_PART,
)

# Material presets
from pyfds.domain.material_presets import (
    MATERIAL_PRESETS, SURFACE_PRESETS,
    list_material_presets, list_surface_presets,
    get_material_preset, get_surface_preset,
    make_material as make_material_preset,
    make_surface as make_surface_preset,
)

# Tenability & Life Safety
from pyfds.tenability import (
    FED_INCAPACITATION, FED_LETHALITY, FEDResult,
    calculate_fed, aset_margin,
    SignType, MASS_OPTICAL_DENSITY, VisibilityResult, VisibilityTimeSeries,
    visibility_from_extinction, visibility_from_smoke_density,
    visibility_from_fds_soot, visibility_timeseries,
    LayerHeightResult, LayerHeightTimeSeries,
    n_percent_interface, layer_height_timeseries,
)


# ---------------------------------------------------------------------------
# Backward compatibility shims (v0.2.0 names)
# ---------------------------------------------------------------------------

# Old flat-module names that tests / existing code may import
try:
    # Old attribute aliases for v0.2.0 names
    Layer            = Material          # v0.2.0 had Material with nested layers
    SmvScriptBuilder = SsfScriptBuilder  # renamed in v0.3.0

    # Old validator class (delegated to ValidationEngine)
    class FdsValidator:                   # type: ignore[no-redef]
        """Compatibility shim — use ValidationEngine in new code."""
        def __init__(self):
            self._engine = ValidationEngine.default()

        def validate(self, project) -> bool:
            report = self._engine.validate(project)
            return report.passed

    # Old utils module-level helpers
    def fds_format_value(value, precision: int = 4) -> str:
        """Compatibility shim for ``fds_format_value``."""
        return fmt_float(value, precision)

    def is_poisson_compliant(nx: int, ny: int, nz: int) -> bool:
        """Compatibility shim for ``is_poisson_compliant``."""
        return GeometryHelper.is_poisson_compliant(nx, ny, nz)

except Exception:
    pass   # non-fatal — only affects legacy shims


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__version__ = "0.3.0"

__all__ = [
    # API
    "FdsApi",

    # Core
    "EventBus", "EventType", "get_global_bus",
    "FdsError", "FdsValidationError", "FdsExecutionError", "FdsParseError",
    "FdsSerializationError", "FdsPluginError", "FdsConfigError",
    "FdsJobError", "FdsNotFoundError", "FdsTimeoutError", "FdsBinaryError",
    "FdsConfig", "get_config",
    "Session", "SessionManager",
    "StateSnapshot", "StateManager", "build_snapshot",
    # Selection
    "SelectionManager", "SelectionMode", "SelectionSnapshot",
    # Viewport
    "ViewportCamera", "ViewportState", "ViewportController",
    "TransformMode", "CameraPreset", "ProjectionMode", "VisibilityFlags", "SnapSettings",

    # Domain — canonical names (as defined in domain/model.py)
    "FdsProject",
    "Mesh", "Obstruction", "Surface", "Vent", "Device", "Material", "Reaction",
    "Ramp", "Control", "Prop", "Particle", "Species",
    "HvacNode", "HvacDuct", "Fan", "Damper",
    "Zone", "Prof",
    "Slice", "BoundaryFile", "IsoSurface",
    "SimulationParams", "DumpParams", "MiscParams", "PresParams", "RadiParams",
    # Phase 1 additions
    "Layer", "MaterialReaction", "Geom", "Plot3D", "MeshTransform",
    "Hole", "Mult", "Init", "Hvac",
    # Gap-fill additions
    "WindProfile", "Move", "HvacFilter", "HvacLeakage", "Smoke3D",
    # v0.3 normalised aliases
    "Spec", "HvacFan", "HvacDamper", "BoundaryOutput", "Isosurface",
    "TimeParams", "PressParams",
    "BoundingBox", "GeometryHelper",
    "MaterialLibrary", "MaterialPreset",
    "PresetEngine", "ScenarioTemplate", "apply_preset", "list_presets",
    # Schema & Factory
    "PropertyDescriptor", "FieldType", "EntitySchema", "SchemaRegistry", "get_schema_registry",
    "EntityFactory",
    # Egress coupling
    "EgressScenario", "ExitZone", "OccupantGroup", "TenabilityLimit",

    # IO
    "FdsParser", "FdsWriter", "Serializer",

    # Validation
    "ValidationEngine", "ValidationReport", "ValidationResult", "Severity",

    # Execution
    "Job", "JobStatus", "SimulationRunner", "JobQueue",
    "ParametricStudy", "BatchExecutor", "BatchReport",
    "BatchStudyConfig", "BatchConfigError", "AxisConfig",

    # Results — core
    "DeviceReader", "LogParser", "SliceReader", "BoundaryReader", "SimulationStats",
    "ResultIndex", "SliceIndex", "BoundaryIndex",
    # Results — Phase 2/3
    "Plot3DReader", "Plot3DResult",
    "ParticleReader", "ParticleResult", "ParticleClass", "ParticleFrame",
    "plot_device_timeseries", "plot_hrr", "plot_slice_contour",
    "plot_multi_quantity", "plot_particle_positions",
    "SimulationReport", "ReportSection",
    "SimulationComparator", "ComparisonReport", "ChannelComparison",
    "BatchResultAnalyzer", "BatchAnalysisReport", "VariantSummary", "ChannelStats",

    # Smokeview — runner, parser, binary, scripting, INI
    "SmokeviewRunner",
    "SmvParser", "SmvMetadata", "SmvGrid", "SmvSlice", "SmvBoundary",
    "SmvIsosurface", "SmvDevice", "SmvPlot3D", "SmvSmoke3D", "SmvParticle",
    "SmvViewpoint", "SmvSurface",
    "SmvBinaryExtractor", "SsfScriptBuilder",
    "SmvIniConfig", "SmvIniWriter", "SmvIniParser",
    "SmvColorbarConfig", "SmvSurfaceColor", "SmvIniUnsupported",

    # Automation
    "ScenarioOrchestrator", "OrchestratorResult",
    "WorkflowEngine", "WorkflowContext", "WorkflowStep",
    "ValidateStep", "WriteStep", "RunStep", "RenderStep", "CollectResultsStep",
    "Command", "CommandPipeline", "CommandResult",
    "AddEntityCommand", "RemoveEntityCommand", "ModifyPropertyCommand",
    "GroupCommand", "DuplicateEntityCommand", "SetHrrCommand", "ScaleCommand",

    # Meshing
    "MeshingManager", "EngineRegistry", "get_engine_registry",
    "MeshingEngineBase", "MeshingEngine",
    "EngineCapabilities", "EngineStatus", "LicenseType", "ElementType",
    "MeshResult", "GeometryResult", "FdsStructuredMesh", "MeshData",
    "StructuredMeshRequest", "SurfaceMeshRequest", "VolumeMeshRequest",
    "GeometryImportRequest",
    "BoundingBoxGeometry", "SurfaceMeshGeometry", "FileGeometry",
    "BuiltinStructuredEngine", "GmshEngine", "TetGenEngine", "NetgenEngine",

    # Plugins
    "PluginBase", "PluginMetadata",
    "PluginLoader", "PluginRegistry", "get_registry",

    # Utils
    "fmt_xb", "fmt_ijk", "fmt_xyz", "fmt_float", "fds_bool", "fds_str",
    "setup_logging", "get_logger",

    # v0.2.0 backward-compat shims
    "FdsValidator", "fds_format_value", "is_poisson_compliant",
    "Layer", "SmvScriptBuilder",

    # Engineering — zone model & detector response
    "ZoneModelResult", "DetectorResponseResult",
    "two_layer_zone_model", "detector_response_time",

    # Reaction library
    "FUEL_LIBRARY", "list_fuels", "get_fuel", "make_reaction",

    # Quantity library
    "FdsQuantity", "QUANTITY_DB",
    "list_quantities", "get_quantity", "quantities_for_context", "validate_quantity",
    "CONTEXT_DEVC", "CONTEXT_SLCF", "CONTEXT_BNDF", "CONTEXT_ISOF",
    "CONTEXT_PL3D", "CONTEXT_PROF", "CONTEXT_PART",

    # Material presets
    "MATERIAL_PRESETS", "SURFACE_PRESETS",
    "list_material_presets", "list_surface_presets",
    "get_material_preset", "get_surface_preset",
    "make_material_preset", "make_surface_preset",

    # Version
    "__version__",
]
