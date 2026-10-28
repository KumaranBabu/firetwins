"""
FDS namelist tokenizer
======================
A small, dependency-free scanner for the Fortran-namelist dialect FDS reads:

    &OBST XB=0,1,0,1,0,1  SURF_ID = 'INERT'   ! comment
          COLOR='RED' /

It knows nothing about FDS entities; it turns text into :class:`NamelistRecord`
objects (tag + parameters + the verbatim source text) and is used by
:class:`pyfds.io.fds_parser.FdsParser`.

Rules implemented (per the FDS User Guide, "Input File Structure"):

* A record starts at ``&TAG`` where ``&`` is the first non-blank character of
  a line (the Fortran namelist rule — so ``#&OBST ...`` is *not* a record), and
  ends at a ``/`` or ``&END`` that is *outside* a quoted string.
* ``!`` starts a comment to end of line — except inside a quoted string.
* Commas between values and between ``KEY=value`` groups are *optional*;
  whitespace also separates. ``KEY = value`` may have spaces around ``=``.
* Strings use ``'..'`` or ``".."``; a doubled quote inside is a literal quote.
* Keys may carry an index: ``MASS_FRACTION(1)``, ``XB(1:3)``, ``PBX(2,3)``.
* ``n*value`` repeat counts are expanded in :attr:`NamelistRecord.params`.
* Text outside records is ignored; commented-out records (``! &OBST ...``,
  ``# &OBST ...``) are skipped. A leading UTF-8 BOM counts as whitespace.
* A record missing its terminator ends where the next ``&TAG`` begins.

Each record exposes two views of its parameters:

``params``
    ``{KEY: value-string}`` in the shape the original regex parser produced
    (comma-joined items; a value that is one quoted string, or a list of quoted
    strings, has its outermost quote characters removed; ``KEY(1)``, ``KEY(2)``...
    that together make a whole array from index 1 are also reachable as ``KEY``)
    so existing entity builders work as-is.

``fields``
    ``[(KEY, fds_text), ...]`` in source order, exactly as written (quotes and
    repeat counts kept, one entry per occurrence). This is what lets the parser
    carry parameters it has no model for through to the writer unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Tuple

__all__ = ["NamelistRecord", "tokenize", "split_values", "base_key", "alias_of"]

# Top level: a record starts with '&' as the first non-blank character of a line.
_TOP_RE = re.compile(r"^[ \t﻿]*&(?P<tag>[A-Za-z]\w*)", re.MULTILINE)

# Inside a record. Order matters (strings before words).
_TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<comment>!.*)
    | (?P<str>'(?:[^'\n]|'')*'|"(?:[^"\n]|"")*")
    | (?P<end>/)
    | (?P<amp>&\w*)
    | (?P<comma>,)
    | (?P<eq>=)
    | (?P<word>[^\s,=/'"!&()]+(?:\([^)\n]*\))?)
    | (?P<other>.)
    """,
    re.VERBOSE,
)

_REPEAT_RE = re.compile(r"^(\d+)\*(.+)$")
_BARE_REPEAT_RE = re.compile(r"^(\d+)\*$")
_SINGLE_INDEX_RE = re.compile(r"\(\d+\)$")


@dataclass
class NamelistRecord:
    """One ``&TAG ... /`` record."""
    tag: str                                   # upper-case
    params: Dict[str, str] = field(default_factory=dict)
    fields: List[Tuple[str, str]] = field(default_factory=list)
    raw: str = ""                              # verbatim source text of the record
    line: int = 0                              # 1-based line of the '&'
    terminated: bool = True
    warnings: List[str] = field(default_factory=list)


def split_values(value: str) -> List[str]:
    """Split a comma-joined value string back into stripped, unquoted items."""
    return [v.strip().strip("'\"") for v in value.split(",") if v.strip()]


def base_key(key: str) -> str:
    """``MASS_FRACTION(1)`` -> ``MASS_FRACTION``; any parenthesised suffix is dropped."""
    i = key.find("(")
    return key if i < 0 else key[:i]


def alias_of(key: str):
    """Base name under which ``params`` also exposes *key*, or ``None``.

    Only a single integer index (``MASS_FRACTION(1)``) is aliased; ranges and
    multi-dimensional indices (``SPEC_ID(1:3)``, ``NU_SPEC(1,2)``) are not.
    """
    return _SINGLE_INDEX_RE.sub("", key) if _SINGLE_INDEX_RE.search(key) else None


def tokenize(text: str) -> Iterator[NamelistRecord]:
    """Yield every namelist record found in *text* (never raises)."""
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOP_RE.search(text, pos)
        if m is None:
            return
        start = m.start() + m.group().index("&")   # skip the leading blanks
        rec, pos = _read_record(text, m.group("tag").upper(), m.end(), start)
        yield rec


def _read_record(text: str, tag: str, body_start: int, start: int) -> Tuple[NamelistRecord, int]:
    toks: List[Tuple[str, str]] = []
    pos = body_start
    n = len(text)
    terminated = False
    end = n
    while pos < n:
        m = _TOKEN_RE.match(text, pos)
        kind = m.lastgroup
        if kind == "end":
            terminated, end = True, m.end()
            break
        if kind == "amp":
            if m.group().upper() == "&END":
                terminated, end = True, m.end()
                break
            line_prefix = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
            if line_prefix.strip(" \t﻿") == "":
                end = m.start()                  # next record began; this one is unterminated
                break
        if kind in ("str", "word", "comma", "eq"):
            toks.append((kind, m.group()))
        pos = m.end()
        end = pos
    rec = NamelistRecord(
        tag=tag,
        raw=text[start:end].rstrip(),
        line=text.count("\n", 0, start) + 1,
        terminated=terminated,
    )
    if not terminated:
        rec.warnings.append(f"&{tag} (line {rec.line}): record has no terminating '/'")
    rec.params, rec.fields = _build_params(toks)
    return rec, end


def _unquote(tok: str) -> str:
    q = tok[0]
    return tok[1:-1].replace(q * 2, q)


def _build_params(toks: List[Tuple[str, str]]) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    params: Dict[str, str] = {}
    fields: List[Tuple[str, str]] = []
    families: Dict[str, Dict[int, List[str]]] = {}
    n = len(toks)
    is_key = [
        toks[i][0] == "word" and i + 1 < n and toks[i + 1][0] == "eq"
        for i in range(n)
    ]
    i = 0
    while i < n:
        if not is_key[i]:
            i += 1
            continue
        raw_key = toks[i][1].upper()
        i += 2                                   # skip KEY and '='
        items: List[str] = []                    # expanded, quotes normalised (-> params)
        source: List[str] = []                   # as written (-> fields)
        while i < n and not is_key[i]:
            kind, text = toks[i]
            if kind == "str":
                items.append("'" + _unquote(text) + "'")
                source.append(text)
            elif kind == "word":
                r = _REPEAT_RE.match(text)
                bare = _BARE_REPEAT_RE.match(text)
                if r:
                    items.extend([r.group(2)] * int(r.group(1)))
                    source.append(text)
                elif bare and i + 1 < n and toks[i + 1][0] == "str":
                    # n*'text': the count is its own token, the string follows
                    nxt = toks[i + 1][1]
                    items.extend(["'" + _unquote(nxt) + "'"] * int(bare.group(1)))
                    source.append(text + nxt)
                    i += 1
                else:
                    items.append(text)
                    source.append(text)
            i += 1
        params[raw_key] = _joined(items)
        m = _SINGLE_INDEX_RE.search(raw_key)
        if m:
            families.setdefault(raw_key[:m.start()], {})[int(m.group()[1:-1])] = items
        fields.append((raw_key, ",".join(source)))
    # KEY(1)=a KEY(2)=b is also reachable as KEY='a,b', but only when the indices make the whole array from 1:
    # a partial one (GVEC(3)=0, SURF_ID6(2)='X') read as KEY would be taken for the full array and lose its meaning.
    for base, parts in families.items():
        if base in params:
            continue
        values: Dict[int, str] = {}
        for start, items in parts.items():
            for off, item in enumerate(items):
                values[start + off] = item
        if sorted(values) == list(range(1, len(values) + 1)):
            params[base] = _joined([values[i] for i in range(1, len(values) + 1)])
    return params, fields


def _joined(items: List[str]) -> str:
    value = ",".join(items)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]                      # legacy shape: strip outermost quotes
    return value
