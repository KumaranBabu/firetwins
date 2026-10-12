"""FdsParser regressions found by round-tripping the 900 FDS example cases."""
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.serializer import Serializer

HEAD = "&HEAD CHID='t' /\n&MESH IJK=5,5,5, XB=0,1,0,1,0,1 /\n"


def parse(body):
    return FdsParser().parse_string(HEAD + body)


def test_obst_with_space_separated_fields_is_not_dropped():
    p = parse("&OBST XB=0,0.5,0,0.5,0,0.5   SURF_ID='INERT' COLOR='RED' /")
    assert len(p.obstructions) == 1 and p.obstructions[0].color == "RED"


def test_slice_with_spaces_around_equals():
    p = parse("&SLCF PBY = 0.025 QUANTITY = 'TEMPERATURE' /")
    assert len(p.slices) == 1


def test_mesh_followed_by_xb_without_comma():
    p = FdsParser().parse_string("&MESH IJK=10,10,10 XB=0,1,0,1,0,1 /")
    assert len(p.meshes) == 1 and tuple(p.meshes[0].cell_count) == (10, 10, 10)


def test_material_with_spaced_assignments_keeps_all_fields():
    p = parse("&MATL ID            = 'Metal'\n      DENSITY       = 5000.\n"
              "      CONDUCTIVITY  = 50.\n      SPECIFIC_HEAT = 1.0 /")
    m = p.materials[0]
    assert (m.density, m.conductivity, m.specific_heat) == (5000.0, 50.0, 1.0)


def test_time_record_with_whitespace_separated_fields():
    p = parse("&TIME T_END=60. DT=0.25 /")
    assert p.params.t_end == 60.0 and p.params.dt == 0.25


def test_string_containing_slash_is_not_truncated():
    p = parse("&DEVC ID='d' XYZ=1,1,1 QUANTITY='TEMPERATURE' UNITS='kg/m2' /")
    assert len(p.devices) == 1 and (p.devices[0].x, p.devices[0].y, p.devices[0].z) == (1.0, 1.0, 1.0)


def test_commented_out_record_is_not_parsed():
    p = parse("#&OBST XB=0,1,0,1,0,1 /\n! &OBST XB=0,1,0,1,0,1 /\n")
    assert p.obstructions == []


# ── unknown namelists are preserved, never dropped ───────────────────────────

CASE = HEAD + "&COMB EXTINCTION_MODEL='EXTINCTION 1' /\n&CLIP MAXIMUM_DENSITY=1.0 /\n"


def test_unknown_namelists_are_kept_verbatim():
    p = FdsParser().parse_string(CASE)
    assert p.raw_records == ["&COMB EXTINCTION_MODEL='EXTINCTION 1' /",
                             "&CLIP MAXIMUM_DENSITY=1.0 /"]


def test_tail_is_not_treated_as_unknown():
    assert FdsParser().parse_string(CASE + "&TAIL /\n").raw_records[-1].startswith("&CLIP")


def test_writer_reemits_raw_records_before_tail():
    out = FdsWriter().to_string(FdsParser().parse_string(CASE))
    assert "&COMB EXTINCTION_MODEL='EXTINCTION 1' /" in out and "&CLIP MAXIMUM_DENSITY=1.0 /" in out
    assert out.index("&COMB") < out.rindex("&TAIL")
    # and the output parses back to the same raw records (stable round trip)
    assert FdsParser().parse_string(out).raw_records == FdsParser().parse_string(CASE).raw_records


def test_raw_records_survive_pyfds_archive_roundtrip():
    p = FdsParser().parse_string(CASE)
    p2 = Serializer().load_string(Serializer().save_string(p))
    assert p2.raw_records == p.raw_records


def test_project_without_raw_records_adds_no_key():
    import json
    p = FdsParser().parse_string(HEAD)
    assert "raw_records" not in json.loads(Serializer().save_string(p))


def test_parser_reports_unterminated_record_as_warning():
    parser = FdsParser()
    parser.parse_string("&MESH IJK=5,5,5 XB=0,1,0,1,0,1\n&TIME T_END=1 /")
    assert any("terminating" in w for w in parser.warnings)


# ── unmodelled parameters are carried through (fds_extra) ────────────────────

def roundtrip(body):
    p = parse(body)
    return p, FdsWriter().to_string(p)


def test_unmodelled_parameters_survive_a_round_trip():
    p, out = roundtrip("&VENT MB='XMIN' SURF_ID='OPEN' COLOR='RED' PBX=0.5 /")
    assert p.vents[0].fds_extra == {"MB": "'XMIN'", "COLOR": "'RED'", "PBX": "0.5"}
    line = next(l for l in out.splitlines() if l.startswith("&VENT"))
    assert "MB='XMIN'" in line and "COLOR='RED'" in line and "PBX=0.5" in line


def test_extras_are_stable_across_repeated_round_trips():
    _, out1 = roundtrip("&DEVC ID='d' XYZ=1,1,1 QUANTITY='TEMPERATURE' SPATIAL_STATISTIC='MEAN' TIME_AVERAGED=.TRUE. /")
    out2 = FdsWriter().to_string(FdsParser().parse_string(out1))
    line = lambda o: next(l for l in o.splitlines() if l.startswith("&DEVC"))
    assert line(out1) == line(out2)
    assert "SPATIAL_STATISTIC='MEAN'" in line(out2)


def test_indexed_and_range_indexed_keys_are_preserved():
    p, out = roundtrip("&INIT XB=0,1,0,1,0,3 SPEC_ID(1:3)='A','B','C' VOLUME_FRACTION(1:3)=0.1,0.3,0.23 /")
    line = next(l for l in out.splitlines() if l.startswith("&INIT"))
    assert "SPEC_ID(1:3)='A','B','C'" in line and "VOLUME_FRACTION(1:3)=0.1,0.3,0.23" in line
    # complex stoichiometry is now typed (RXN-01): the indexed form becomes arrays and round-trips
    p, out = roundtrip("&REAC FUEL='PROPANE' SPEC_ID_NU(1)='A' SPEC_ID_NU(2)='B' NU(1)=-1 NU(2)=1 /")
    assert p.reactions[0].spec_id_nu == ["A", "B"] and p.reactions[0].nu == [-1.0, 1.0]
    again = FdsParser().parse_string(out)
    assert again.reactions[0].spec_id_nu == ["A", "B"] and again.reactions[0].nu == [-1.0, 1.0]
    assert not again.reactions[0].fds_extra
    # an index gap cannot be a list: kept verbatim instead
    p, out = roundtrip("&REAC FUEL='PROPANE' SPEC_ID_NU(1)='A' SPEC_ID_NU(3)='B' NU(1)=-1 NU(3)=1 /")
    line = next(l for l in out.splitlines() if l.startswith("&REAC"))
    assert p.reactions[0].spec_id_nu is None
    for frag in ("SPEC_ID_NU(3)='B'", "NU(3)=1"):
        assert frag in line


def test_singleton_namelists_keep_extras():
    p, out = roundtrip("&MISC SIMULATION_MODE='LES' CFL_MAX=0.9 /\n&DUMP DT_SL3D=0.25 /\n&TIME T_END=5 WALL_INCREMENT=2 /")
    assert p.misc.fds_extra == {"SIMULATION_MODE": "'LES'", "CFL_MAX": "0.9"}
    for frag in ("SIMULATION_MODE='LES'", "CFL_MAX=0.9", "DT_SL3D=0.25", "WALL_INCREMENT=2"):
        assert frag in out


def test_head_extras_survive():
    p = FdsParser().parse_string("&HEAD CHID='t' TITLE='x' SAVE_RESTART=.TRUE. /")
    assert p.head_extra == {"SAVE_RESTART": ".TRUE."}
    assert "SAVE_RESTART=.TRUE." in FdsWriter().to_string(p)


def test_fds_extra_survives_pyfds_archive():
    p = parse("&VENT MB='XMIN' SURF_ID='OPEN' /")
    p2 = Serializer().load_string(Serializer().save_string(p))
    assert p2.vents[0].fds_extra == {"MB": "'XMIN'"}


def test_no_fds_extra_when_everything_is_modelled():
    p = parse("&OBST XB=0,1,0,1,0,1 SURF_ID='INERT' /")
    assert p.obstructions[0].fds_extra is None


# ── writer/parser fidelity fixes ─────────────────────────────────────────────

def line_of(out, tag):
    return next(l for l in out.splitlines() if l.startswith("&" + tag))


def test_noise_false_is_written_and_default_true_is_not():
    _, out = roundtrip("&MISC NOISE=.FALSE. /")
    assert "NOISE=.FALSE." in line_of(out, "MISC")
    _, out = roundtrip("&MISC TMPA=20. /")
    assert "NOISE" not in line_of(out, "MISC")


def test_p_inf_and_suppression_are_written_when_not_default():
    _, out = roundtrip("&MISC P_INF=90630 SUPPRESSION=.FALSE. /")
    m = line_of(out, "MISC")
    assert "P_INF=90630" in m and "SUPPRESSION=.FALSE." in m


def test_dt_restart_round_trips():
    _, out = roundtrip("&DUMP DT_RESTART=15.0 /")
    assert "DT_RESTART=15.0" in line_of(out, "DUMP")
    _, out = roundtrip("&DUMP DT_SLCF=2 /")
    assert "DT_RESTART" not in line_of(out, "DUMP")


def test_single_reaction_material_keeps_n_reactions():
    _, out = roundtrip("&MATL ID='F' DENSITY=100 CONDUCTIVITY=0.2 SPECIFIC_HEAT=1 N_REACTIONS=1 A=1.e4 E=1.e5 HEAT_OF_REACTION=800 /")
    assert "N_REACTIONS=1" in line_of(out, "MATL")


def test_multi_input_control_uses_valid_input_id_keyword():
    _, out = roundtrip("&CTRL ID='c' FUNCTION_TYPE='POWER' INPUT_ID='a','CONSTANT' CONSTANT=2 /")
    c = line_of(out, "CTRL")
    assert "INPUT_ID=" in c and "INPUT_IDS" not in c


def test_init_point_source_keeps_xyz_and_gets_no_invented_box():
    p, out = roundtrip("&INIT PART_ID='ball' XYZ=0.5,0.0,0.5 N_PARTICLES=1 /")
    line = line_of(out, "INIT")
    assert "XYZ=0.5,0.0,0.5" in line and "XB=" not in line


def test_mpi_process_zero_is_kept():
    p, out = roundtrip("&MESH IJK=5,5,5 XB=0,1,0,1,0,1 MPI_PROCESS=0 /")
    assert p.meshes[1].mpi_processor == 0       # [0] is the mesh in the test header
    assert "MPI_PROCESS=0" in out


def test_geom_faces_with_surface_index_are_preserved_verbatim():
    _, out = roundtrip("&GEOM ID='G' SURF_ID='S' VERTS=0,0,0,1,0,0,0,1,0,0,0,1 FACES=1,2,3,1,1,3,4,1 /")
    assert "FACES=1,2,3,1,1,3,4,1" in line_of(out, "GEOM")


def test_geom_triangle_faces_still_modelled():
    p = parse("&GEOM ID='G' SURF_ID='S' VERTS=0,0,0,1,0,0,0,1,0 FACES=1,2,3 /")
    assert p.geoms[0].faces == [(1, 2, 3)]


def test_extra_never_duplicates_a_key_the_writer_already_wrote():
    # INITIAL_STATE is written from the model AND present in the source: one copy, source value wins
    _, out = roundtrip("&DEVC ID='d' XYZ=1,1,1 QUANTITY='TEMPERATURE' INITIAL_STATE=.TRUE. /")
    line = line_of(out, "DEVC")
    assert line.count("INITIAL_STATE") == 1 and "INITIAL_STATE=.TRUE." in line
    # and a second pass is a fixed point
    out2 = FdsWriter().to_string(FdsParser().parse_string(out))
    assert line_of(out2, "DEVC") == line


def test_unmodelled_string_with_slash_and_quote_survives():
    p, out = roundtrip("&VENT XB=0,1,0,1,0,0 SURF_ID='OPEN' SMOKEVIEW_LABEL='a/b it''s' /")
    assert "SMOKEVIEW_LABEL='a/b it''s'" in line_of(out, "VENT")
