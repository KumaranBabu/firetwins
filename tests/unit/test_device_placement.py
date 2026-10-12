"""Regression: devices created with ``xyz=[...]`` must end up there (found by the demo case: every device sat at 0,0,0)."""
from __future__ import annotations

from pyfds.api import FdsApi
from pyfds.domain.model import Device
from pyfds.io.fds_writer import FdsWriter


def test_xyz_keyword_places_the_device():
    d = Device(xyz=[3.0, 2.4, 2.3], name="a")
    assert (d.x, d.y, d.z) == (3.0, 2.4, 2.3)


def test_api_constructors_and_export_keep_the_position():
    api = FdsApi()
    api.devices.add_thermocouple([1.0, 2.0, 3.0], "TC")
    api.devices.add_device("VELOCITY", [4.0, 5.0, 6.0], name="V")
    api.props.add_heat_detector("DET")
    api.devices.add_sprinkler([7.0, 8.0, 9.0], "DET")
    text = FdsWriter().generate_content(api.project)
    assert "ID='TC', QUANTITY='TEMPERATURE', XYZ=1.0,2.0,3.0" in text
    assert "ID='V', QUANTITY='VELOCITY', XYZ=4.0,5.0,6.0" in text
    assert "XYZ=7.0,8.0,9.0" in text
    assert "XYZ=0.0,0.0,0.0" not in text


def test_explicit_xyz_fields_are_not_overwritten():
    d = Device(x=1.0, y=1.0, z=1.0, xyz=[9.0, 9.0, 9.0], name="b")
    assert (d.x, d.y, d.z) == (1.0, 1.0, 1.0)
