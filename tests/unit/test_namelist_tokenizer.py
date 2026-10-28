"""Unit tests for the FDS namelist tokenizer (pyfds.io.namelist)."""
import pytest

from pyfds.io.namelist import split_values, tokenize


def one(text):
    recs = list(tokenize(text))
    assert len(recs) == 1, recs
    return recs[0]


# ── separators ───────────────────────────────────────────────────────────────

def test_commas_between_fields_are_optional():
    r = one("&OBST XB=0,0.5,0,0.01,0,0.2   SURF_ID='INERT' COLOR='RED' /")
    assert r.params == {"XB": "0,0.5,0,0.01,0,0.2", "SURF_ID": "INERT", "COLOR": "RED"}


def test_spaces_around_equals_sign():
    r = one("&SLCF PBY = 0.025 QUANTITY = 'TEMPERATURE' /")
    assert r.params == {"PBY": "0.025", "QUANTITY": "TEMPERATURE"}


def test_values_separated_by_spaces_and_commas_mixed():
    assert one("&MESH IJK=10 20,30  XB=0 1 0 1 0 1/").params == {
        "IJK": "10,20,30", "XB": "0,1,0,1,0,1"}


def test_multiline_record_and_trailing_commas():
    r = one("&SURF ID='A',\n      RGB=1,2,3,\n      HRRPUA=500.\n/")
    assert r.params == {"ID": "A", "RGB": "1,2,3", "HRRPUA": "500."}


def test_tag_is_uppercased_and_keys_too():
    r = one("&obst xb=0,1,0,1,0,1 surf_id='a' /")
    assert r.tag == "OBST" and set(r.params) == {"XB", "SURF_ID"}


# ── strings ──────────────────────────────────────────────────────────────────

def test_slash_inside_string_does_not_end_the_record():
    r = one("&DEVC ID='d' QUANTITY='TEMPERATURE' UNITS='kg/m2' XYZ=1,2,3 /")
    assert r.params["UNITS"] == "kg/m2" and r.params["XYZ"] == "1,2,3"


def test_exclamation_inside_string_is_not_a_comment():
    assert one("&HEAD TITLE='Hello! World' /").params["TITLE"] == "Hello! World"


def test_equals_inside_string_is_not_a_key():
    r = one("&PROP ID='p' SMOKEVIEW_PARAMETERS(1:3)='R=255','G=0','B=0' /")
    assert set(r.params) == {"ID", "SMOKEVIEW_PARAMETERS(1:3)"}
    assert split_values(r.params["SMOKEVIEW_PARAMETERS(1:3)"]) == ["R=255", "G=0", "B=0"]


def test_doubled_quote_is_an_escaped_quote():
    assert one("&HEAD TITLE='it''s fine' /").params["TITLE"] == "it's fine"


def test_double_quoted_strings():
    assert one('&HEAD CHID="case_1" /').params["CHID"] == "case_1"


def test_list_of_strings_keeps_legacy_shape():
    # legacy shape: outermost quotes stripped, inner separators kept
    v = one("&OBST XB=0,1,0,1,0,1 SURF_IDS='A','B','C' /").params["SURF_IDS"]
    assert split_values(v) == ["A", "B", "C"]


# ── comments and record boundaries ───────────────────────────────────────────

def test_comment_after_value_and_between_fields():
    r = one("&OBST XB=0,1,0,1,0,1 ! the box\n SURF_ID='A' /")
    assert r.params["SURF_ID"] == "A"


def test_commented_out_records_are_skipped():
    text = "! &OBST XB=9,9,9,9,9,9 /\n#&OBST XB=8,8,8,8,8,8 /\n&OBST XB=0,1,0,1,0,1 /"
    recs = list(tokenize(text))
    assert [r.params["XB"] for r in recs] == ["0,1,0,1,0,1"]


def test_leading_whitespace_and_bom_before_ampersand():
    recs = list(tokenize("﻿&HEAD CHID='a'/\n   &TAIL /"))
    assert [r.tag for r in recs] == ["HEAD", "TAIL"]


def test_text_outside_records_is_ignored():
    recs = list(tokenize("some prose with 'quote and & ampersand\n&TIME T_END=5 /\ntrailing"))
    assert [r.tag for r in recs] == ["TIME"]


def test_unterminated_record_ends_at_next_record():
    recs = list(tokenize("&SLCF PBY=0.5 QUANTITY='T'\n&TIME T_END=1 /"))
    assert [r.tag for r in recs] == ["SLCF", "TIME"]
    assert not recs[0].terminated and recs[0].warnings
    assert recs[1].terminated and recs[1].params == {"T_END": "1"}


def test_amp_end_terminator():
    r = one("&HEAD CHID='x' &END")
    assert r.terminated and r.params == {"CHID": "x"}


def test_empty_record_and_tail():
    recs = list(tokenize("&TAIL /"))
    assert recs[0].tag == "TAIL" and recs[0].params == {}


# ── indices, repeats ─────────────────────────────────────────────────────────

def test_indexed_keys_store_full_and_base_name():
    r = one("&REAC SPEC_ID_NU(1)='A' SPEC_ID_NU(2)='B' MASS_FRACTION(1)=0.5 /")
    assert r.params["SPEC_ID_NU(1)"] == "A" and r.params["SPEC_ID_NU(2)"] == "B"
    assert split_values(r.params["SPEC_ID_NU"]) == ["A", "B"]     # the base name holds the whole array
    assert r.params["MASS_FRACTION(1)"] == "0.5" and r.params["MASS_FRACTION"] == "0.5"


def test_a_partial_array_gets_no_base_alias():
    r = one("&MISC GVEC(3)=0 /")                   # only the z component: read as GVEC it would mean (0, ?, ?)
    assert r.params["GVEC(3)"] == "0" and "GVEC" not in r.params
    r = one("&OBST XB=0,1,0,1,0,1 SURF_ID6(2)='A', SURF_ID6(4:5)='B','C' /")
    assert "SURF_ID6" not in r.params


def test_range_and_multi_dimensional_indices_are_not_split():
    r = one("&PROP ID='p' PART_ID='x' PBX(2,3)=1.5 /")
    assert r.params["PBX(2,3)"] == "1.5"


def test_repeat_counts_are_expanded():
    assert one("&OBST XB=0,1,0,1,0,1 SURF_IDS=3*'INERT' /").params["SURF_IDS"].count("INERT") == 3
    assert one("&INIT MASS_FRACTION(1)=2*0.5 /").params["MASS_FRACTION(1)"] == "0.5,0.5"


def test_logicals_and_numbers_pass_through_verbatim():
    r = one("&MISC DNS=.TRUE. TMPA=20. NOISE=F /")
    assert r.params == {"DNS": ".TRUE.", "TMPA": "20.", "NOISE": "F"}


# ── bookkeeping ──────────────────────────────────────────────────────────────

def test_raw_text_and_line_numbers():
    text = "&HEAD CHID='a'/\n\n&OBST XB=0,1,0,1,0,1\n      SURF_ID='A' /\n"
    recs = list(tokenize(text))
    assert recs[1].line == 3
    assert recs[1].raw == "&OBST XB=0,1,0,1,0,1\n      SURF_ID='A' /"


def test_never_raises_on_garbage():
    for junk in ["&", "&&&", "&X '", "&X ===", "&X (((", "\x00\x01&A B=", "&A B='unterminated"]:
        list(tokenize(junk))


def test_duplicate_key_last_wins():
    assert one("&X A=1 A=2 /").params["A"] == "2"
