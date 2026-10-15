"""Find and replace over names, tags and descriptions: ``api.find`` (UX-12)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

FIELDS = ("name", "tags", "description")
_NOT_REFERENCES = {"name", "description", "tags", "color"}


@dataclass
class Match:
    entity: Any
    collection: str
    field: str
    value: str


class FindManager:
    def __init__(self, api) -> None:
        self._api = api

    # -- helpers ---------------------------------------------------------------------
    @staticmethod
    def _pattern(text: str, regex: bool, case_sensitive: bool, whole_word: bool):
        if not text:
            raise ValueError("nothing to search for")
        body = text if regex else re.escape(text)
        if whole_word:
            body = rf"(?<![\w]){body}(?![\w])"
        try:
            return re.compile(body, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"bad pattern: {exc}") from None

    def _collections(self, kinds: Optional[Iterable[str]]) -> Dict[str, list]:
        p = self._api.project
        names = sorted(set(p._TYPE_MAP.values()))
        if kinds is not None:
            wanted = set(kinds)
            unknown = wanted - set(names)
            if unknown:
                raise KeyError(f"unknown kind(s): {', '.join(sorted(unknown))}")
            names = [n for n in names if n in wanted]
        return {n: getattr(p, n) for n in names}

    @staticmethod
    def _check_fields(fields: Sequence[str]) -> None:
        bad = [f for f in fields if f not in FIELDS]
        if bad:
            raise ValueError(f"cannot search {', '.join(bad)}; choose from {', '.join(FIELDS)}")

    # -- find -------------------------------------------------------------------------
    def find(self, text: str, fields: Sequence[str] = ("name", "tags"), kinds: Optional[Iterable[str]] = None,
             regex: bool = False, case_sensitive: bool = False, whole_word: bool = False,
             select: bool = False) -> List[Match]:
        self._check_fields(fields)
        pat = self._pattern(text, regex, case_sensitive, whole_word)
        out: List[Match] = []
        for coll, items in self._collections(kinds).items():
            for e in items:
                for f in fields:
                    values = getattr(e, f, None)
                    values = values if isinstance(values, (list, tuple)) else [values]
                    for v in values:
                        if isinstance(v, str) and pat.search(v):
                            out.append(Match(e, coll, f, v))
        if select:
            seen, ents = set(), []
            for m in out:
                if m.entity.uid not in seen:
                    seen.add(m.entity.uid)
                    ents.append(m.entity)
            self._api.selection.select_many(ents)
        return out

    # -- replace ----------------------------------------------------------------------
    def replace(self, find: str, replacement: str, fields: Sequence[str] = ("name",),
                kinds: Optional[Iterable[str]] = None, regex: bool = False, case_sensitive: bool = False,
                whole_word: bool = False, update_references: bool = False, dry_run: bool = False) -> Dict[str, list]:
        """Replace text in names, tags and/or descriptions as ONE undo step.

        A new name must be non-empty and unused in its collection. A renamed object that other objects
        refer to (a surface used by obstructions...) is skipped unless ``update_references`` is true,
        which also rewrites the references. Returns ``{"changed": [...], "skipped": [...]}``."""
        from pyfds.automation.commands import ModifyPropertyCommand
        self._check_fields(fields)
        pat = self._pattern(find, regex, case_sensitive, whole_word)
        sub = (lambda m: replacement) if not regex else replacement
        project = self._api.project
        colls = self._collections(kinds)
        taken = {c: {getattr(e, "name", None) for e in items} for c, items in colls.items()}
        changed, skipped, ops = [], [], []
        for coll, items in colls.items():
            for e in items:
                if "name" in fields and isinstance(getattr(e, "name", None), str) and pat.search(e.name):
                    old, new = e.name, pat.sub(sub, e.name)
                    if new == old:
                        pass
                    elif not new.strip():
                        skipped.append((old, "new name is empty"))
                    elif new in taken[coll]:
                        skipped.append((old, f"{new!r} already exists"))
                    else:
                        ref_ops = [op for r in project.all_entities if r is not e
                                   for op in self._reference_ops(r, old, new)]
                        if ref_ops and not update_references:
                            skipped.append((old, f"referenced by {len(ref_ops)} field(s); use update_references"))
                        else:
                            taken[coll].discard(old)
                            taken[coll].add(new)
                            ops.append(ModifyPropertyCommand(e, "name", new))
                            ops.extend(ref_ops)
                            changed.append((coll, old, new))
                if "description" in fields and isinstance(getattr(e, "description", None), str) and pat.search(e.description):
                    new = pat.sub(sub, e.description)
                    if new != e.description:
                        ops.append(ModifyPropertyCommand(e, "description", new))
                        changed.append((coll, f"{getattr(e, 'name', '?')}.description", new))
                if "tags" in fields and getattr(e, "tags", None):
                    new_tags = [pat.sub(sub, t) for t in e.tags]
                    if new_tags != list(e.tags):
                        ops.append(ModifyPropertyCommand(e, "tags", list(dict.fromkeys(new_tags))))
                        changed.append((coll, f"{getattr(e, 'name', '?')}.tags", new_tags))
        if ops and not dry_run:
            from pyfds.automation.commands import GroupCommand
            result = self._api.history.execute(GroupCommand(ops, label=f"replace {find!r} with {replacement!r}"))
            if not result.success:
                raise ValueError(result.message)
        return {"changed": changed, "skipped": skipped}

    @staticmethod
    def _reference_ops(entity: Any, old: str, new: str) -> list:
        from pyfds.automation.commands import ModifyPropertyCommand
        ops = []
        for field in type(entity).model_fields:
            if field in _NOT_REFERENCES:
                continue
            v = getattr(entity, field, None)
            if isinstance(v, str) and v == old:
                ops.append(ModifyPropertyCommand(entity, field, new))
            elif isinstance(v, list) and old in v:
                ops.append(ModifyPropertyCommand(entity, field, [new if x == old else x for x in v]))
        return ops
