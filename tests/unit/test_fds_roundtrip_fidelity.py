"""Import -> export keeps what FDS would read: arrays given by index, ramps the editor cannot hold, initial wind,
records a builder rejects, and every digit of a number. Each case comes from a file of the FDS example set."""
from __future__ import annotations

import pytest

from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.namelist import split_values, tokenize


def _round_trip(body: str):
    parser = FdsParser()
    project = parser.parse_string("&HEAD CHID='t' /\n&MESH IJK=10,10,10, XB=0,1,0,1,0,1 /\n" + body + "\n&TAIL /\n")
    return project, FdsWriter().to_string(project), parser.warnings


def _records(text, tag):
    return [r for r in tokenize(text) if r.tag == tag]


def _resolved(rec, key):
    """KEY as FDS reads it: KEY=a,b then KEY(n)=c overwrite element by element, in order."""
    values = {}
    for k, text in rec.fields:
        if k == key:
            values = dict(enumerate(split_values(text), start=1))
        elif k.startswith(key + "(") and k.endswith(")") and k[len(key) + 1:-1].isdigit():
            start = int(k[len(key) + 1:-1])
            for off, v in enumerate(split_values(text)):
                values[start + off] = v
    return values


# -- arrays given by index ---------------------------------------------------------------------------------------
def test_one_gvec_component_keeps_its_meaning():
    _, out, _ = _round_trip("&MISC GVEC(3)=0 /")
    assert float(_resolved(_records(out, "MISC")[0], "GVEC")[3]) == 0.0          # zero gravity stays zero gravity


def test_partial_surf_id6_and_short_surf_ids_are_written_back():
    _, out, _ = _round_trip("&SURF ID='SUCK', VEL=1 /\n&SURF ID='Fire', HRRPUA=500 /\n"
                            "&OBST ID='box', XB=0.4,0.6,0.4,0.6,0.3,0.6, SURF_ID6(2)='SUCK' /\n"
                            "&OBST ID='burner', XB=0.1,0.2,0.1,0.2,0,0.1, SURF_IDS='Fire' /")
    box, burner = (next(r for r in _records(out, "OBST") if r.params["ID"] == n) for n in ("box", "burner"))
    assert _resolved(box, "SURF_ID6")[2] == "SUCK"
    assert _resolved(burner, "SURF_IDS")[1] == "Fire"


def test_init_mass_fractions_by_index_are_all_kept():
    project, out, _ = _round_trip("&INIT XB=0,1,0,1,0,1 MASS_FRACTION(1)=0.108, MASS_FRACTION(2)=0.052, "
                                  "MASS_FRACTION(3)=0.003 SPEC_ID='OXYGEN','CARBON DIOXIDE','CARBON MONOXIDE' /")
    assert project.inits[0].mass_fractions == [0.108, 0.052, 0.003]
    mf = _resolved(_records(out, "INIT")[0], "MASS_FRACTION")
    assert [float(mf[i]) for i in (1, 2, 3)] == [0.108, 0.052, 0.003]


def test_a_value_the_model_cannot_hold_passes_through():
    _, out, _ = _round_trip("&MATL ID='FOAM', DENSITY=20, CONDUCTIVITY=0.2, SPECIFIC_HEAT=1, N_REACTIONS=1, "
                            "NU_SPEC=0.5,0.5, HEAT_OF_COMBUSTION=50000,50000, SPEC_ID='METHANE','PROPANE' /")
    assert split_values(_records(out, "MATL")[0].params["HEAT_OF_COMBUSTION"]) == ["50000", "50000"]


@pytest.mark.parametrize("text", ["SMOKEVIEW_PARAMETERS(1)='D=0.01'", "SMOKEVIEW_PARAMETERS(1:3)='R=255','G=0','B=0'"])
def test_smokeview_parameters_are_strings(text):
    project, out, _ = _round_trip(f"&PROP ID='ball', SMOKEVIEW_ID='SPHERE', {text} /")
    written = _resolved(_records(out, "PROP")[0], "SMOKEVIEW_PARAMETERS")
    assert list(written.values()) == project.props[0].smokeview_parameters and "=" in written[1]


def test_plot3d_quantity_stays_in_its_slot():
    _, out, _ = _round_trip("&DUMP PLOT3D_QUANTITY(1)='PRESSURE', PLOT3D_QUANTITY(5)='MASS FRACTION', "
                            "PLOT3D_SPEC_ID(5)='HELIUM' /")
    dump = _records(out, "DUMP")[0]
    assert dump.params["PLOT3D_QUANTITY(5)"] == "MASS FRACTION" and "PLOT3D_QUANTITY(2)" not in dump.params


# -- ramps -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lines", [
    ["&RAMP ID='times', T=0.0 /", "&RAMP ID='times', T=0.28 /"],                       # time list for RAMP_UVW
    ["&RAMP ID='linear ramp', X=0, F=0 /", "&RAMP ID='linear ramp', X=10, F=10 /"],    # spatial ramp
    ["&RAMP ID='T RAMP',EXTERNAL_FILE=T,INITIAL_VALUE=0.081633/"],                     # values from a file
    ["&RAMP ID='r', T=0, F=0, CTRL_ID_DEP='c' /", "&RAMP ID='r', T=10, F=1 /"],        # key the editor lacks
    ["&RAMP ID='back', T=5, F=1 /", "&RAMP ID='back', T=2, F=0 /"],                     # T not increasing
])
def test_a_ramp_the_editor_cannot_hold_is_written_unchanged(lines):
    project, out, warnings = _round_trip("\n".join(lines))
    assert project.ramps == []
    assert [ln for ln in out.splitlines() if ln.startswith("&RAMP")] == lines
    assert any("kept unchanged as text" in w for w in warnings)


def test_a_plain_ramp_is_still_editable():
    project, _, _ = _round_trip("&RAMP ID='q', T=0, F=0 /\n&RAMP ID='q', T=30, F=1 /")
    assert project.ramps[0].times == [0.0, 30.0]


def test_a_ramp_kept_as_text_counts_as_defined():
    from pyfds.validation.rules.references import ReferenceIntegrityRule
    project, _, _ = _round_trip("&SURF ID='hot', TMP_FRONT=1000, RAMP_Q='T RAMP' /\n"
                                "&RAMP ID='T RAMP',EXTERNAL_FILE=T,INITIAL_VALUE=0.08/")
    assert not [r for r in ReferenceIntegrityRule().check(project) if "T RAMP" in r.message]


# -- wind, meshes, rejected records ----------------------------------------------------------------------------------
def test_initial_wind_shares_the_only_wind_line():
    _, out, _ = _round_trip("&WIND U0=1., W0=1., STRATIFICATION=.FALSE. /")
    (wind,) = _records(out, "WIND")                                   # FDS reads a single &WIND line
    assert float(wind.params["U0"]) == 1.0 and float(wind.params["W0"]) == 1.0
    assert wind.params["STRATIFICATION"] == ".FALSE."


def test_initial_wind_survives_misc_pass_through_parameters():
    _, out, _ = _round_trip("&MISC FLUX_LIMITER='SUPERBEE' /\n&WIND U0=1. /")
    (wind,) = _records(out, "WIND")
    assert float(wind.params["U0"]) == 1.0
    assert _records(out, "MISC")[0].params["FLUX_LIMITER"] == "SUPERBEE"


def test_mesh_with_reversed_xb_is_the_same_box():
    project, _, _ = _round_trip("&MESH ID='m2', IJK=14,18,32, XB=0.85,0.15,-0.45,0.45,0,1.6 /")
    m = next(m for m in project.meshes if m.name == "m2")
    assert (m.x_min, m.x_max) == (0.15, 0.85)


def test_line_device_keeps_its_direction():
    _, out, _ = _round_trip("&DEVC ID='line', QUANTITY='U-VELOCITY', XB=0.9,0.1,0.5,0.5,0.5,0.5, POINTS=9 /")
    xb = [float(v) for v in split_values(_records(out, "DEVC")[0].params["XB"])]
    assert xb[:2] == [0.9, 0.1]


def test_a_record_a_builder_rejects_is_kept_as_text():
    project, out, warnings = _round_trip("&OBST ID='bad', XB=0,1,0,1,0 /")
    assert "&OBST ID='bad', XB=0,1,0,1,0 /" in out.splitlines()
    assert not any(o.name == "bad" for o in project.obstructions)
    assert any("kept unchanged as text" in w for w in warnings)


# -- numbers -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [1.575745, 4.34299846494, 0.000244140625, 1.570796326794897, 243738.74668, 6.02e23, 1.2e-9])
def test_numbers_keep_every_digit(value):
    from pyfds.io.fds_writer_common import _fmt_float
    assert float(_fmt_float(value)) == value


@pytest.mark.parametrize("value,text", [(800.0, "800.00"), (1.0, "1.0"), (0.5, "0.5"), (20.0, "20.0")])
def test_short_numbers_keep_the_usual_style(value, text):
    from pyfds.io.fds_writer_common import _fmt_float
    assert _fmt_float(value) == text
