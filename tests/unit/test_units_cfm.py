"""'cfm' (and other typed units) are accepted for volumetric flow, as in PyroSim 2025.1."""
from __future__ import annotations

import pytest

from pyfds.api import FdsApi
from pyfds.domain import units


def test_cfm_is_a_volumetric_flow_unit():
    assert units.parse_with_unit("1000 cfm", "volume_flow") == pytest.approx(0.4719474, rel=1e-6)
    assert units.parse_with_unit("1000CFM", "volume_flow") == pytest.approx(0.4719474, rel=1e-6)
    assert units.parse_with_unit("2 ft3/min", "volume_flow") == pytest.approx(units.parse_with_unit("2 cfm", "volume_flow"))
    assert units.parse_with_unit("5 m^3/s", "volume_flow") == 5.0 and units.parse_with_unit("30 L/s", "volume_flow") == pytest.approx(0.03)


def test_a_bare_number_follows_the_unit_system_and_a_wrong_unit_is_refused():
    assert units.parse_with_unit("2", "volume_flow", "SI") == 2.0
    assert units.parse_with_unit("2", "volume_flow", "EN") == pytest.approx(2 * 0.3048 ** 3)
    with pytest.raises(ValueError, match="unknown unit"):
        units.parse_with_unit("3 furlongs", "volume_flow")
    with pytest.raises(ValueError):
        units.parse_with_unit("abc cfm", "volume_flow")


def test_the_api_parses_with_a_unit():
    api = FdsApi()
    assert api.units.parse("500 cfm", "volume_flow") == pytest.approx(0.2359737, rel=1e-5)
    assert api.units.parse("10 ft", "length") == pytest.approx(3.048)
