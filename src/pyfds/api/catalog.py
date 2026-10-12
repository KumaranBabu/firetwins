"""Read-only catalogs adapters need (quantity names, fuels, presets).

Adapters (agent, cli, gui) import these from ``pyfds.api`` instead of reaching
into ``pyfds.domain`` — see ``tests/architecture``.
"""
from pyfds.domain.material_presets import list_material_presets, list_surface_presets  # noqa: F401
from pyfds.domain.quantities import list_quantities  # noqa: F401
from pyfds.domain.control_functions import list_control_functions  # noqa: F401
from pyfds.domain.reactions import list_fuels  # noqa: F401

__all__ = ["list_control_functions", "list_material_presets", "list_surface_presets", "list_quantities", "list_fuels"]
