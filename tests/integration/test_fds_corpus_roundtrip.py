"""Round-trip the FDS example cases through FdsParser/FdsWriter.

The FDS install ships ~900 verification cases. They are an excellent
real-world regression corpus: parsing must never raise, and (almost) every
``&NAMELIST`` record *and* every parameter inside it must survive parse -> write.

Skipped automatically when the FDS examples are not installed.
"""
import collections
import glob
import re
from pathlib import Path

import pytest

from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.namelist import base_key, tokenize

EXAMPLES = Path(__file__).resolve().parents[2] / "fds_smv" / "FDS6" / "Examples"
FILES = sorted(glob.glob(str(EXAMPLES / "**" / "*.fds"), recursive=True))

pytestmark = pytest.mark.skipif(not FILES, reason="FDS example cases not installed")

_NL = re.compile(r"^[ \t﻿]*&([A-Za-z0-9_]+)", re.M)


def _record_counts(text):
    return collections.Counter(m.group(1).upper() for m in _NL.finditer(text))


def _param_counts(text):
    c = collections.Counter()
    for r in tokenize(text):
        if r.tag in ("RAMP", "TAIL"):
            continue
        for k in {base_key(x) for x in r.params}:
            c[(r.tag, k)] += 1
    return c


@pytest.fixture(scope="module")
def corpus():
    """One parse+write pass over every example, collecting all the metrics."""
    rec_in = rec_kept = param_in = param_kept = clean = 0
    lost_records = collections.Counter()
    errors = []
    for f in FILES:
        text = Path(f).read_text(encoding="utf-8", errors="ignore")
        try:
            out = FdsWriter().to_string(FdsParser().parse_string(text))
        except Exception as exc:                     # pragma: no cover - the assertion reports it
            errors.append((f, repr(exc)))
            continue
        a, b = _record_counts(text), _record_counts(out)
        file_lost = 0
        for tag, n in a.items():
            if tag == "RAMP":
                continue
            kept = min(n, b.get(tag, 0))
            rec_in += n
            rec_kept += kept
            if kept < n:
                lost_records[tag] += n - kept
                file_lost += n - kept
        clean += file_lost == 0
        pa, pb = _param_counts(text), _param_counts(out)
        for key, n in pa.items():
            param_in += n
            param_kept += min(n, pb.get(key, 0))
    return dict(files=len(FILES), clean=clean, errors=errors, lost_records=lost_records,
                rec_in=rec_in, rec_kept=rec_kept, param_in=param_in, param_kept=param_kept)


def test_every_example_parses_and_writes(corpus):
    assert corpus["errors"] == []


def test_record_retention_is_at_least_99_9_percent(corpus):
    r = corpus
    retention = r["rec_kept"] / r["rec_in"]
    assert retention >= 0.999, f"retention {retention:.4%}, lost by tag: {dict(r['lost_records'])}"


def test_at_least_99_percent_of_files_lose_no_record(corpus):
    assert corpus["clean"] / corpus["files"] >= 0.99, dict(corpus["lost_records"])


def test_previously_unsupported_namelists_are_now_preserved(corpus):
    for tag in ("COMB", "CATF", "CLIP", "SM3D", "TABL", "BACK", "CSVF"):
        assert corpus["lost_records"].get(tag, 0) == 0, tag


def test_parameter_retention_is_at_least_99_5_percent(corpus):
    kept, total = corpus["param_kept"], corpus["param_in"]
    assert kept / total >= 0.995, f"{kept}/{total} = {kept / total:.3%}"
