"""Deterministic comparison engine.

The AI agent decides *what* belongs together (column meaning, column mapping,
key columns) and explains the results; this module does the exact, repeatable
comparison so that no difference is ever missed or hallucinated.
"""
from __future__ import annotations

import difflib
import re
from typing import Iterable, Optional

from .models import (ArxmlModel, CodeModel, ColumnMapping, CompareResult, DiffItem,
                     ParsedDocument, SideBySideRow, Table, TextBlock)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_MEANING_HINTS = [
    (r"\b(start|position|pos|startbit)\b", "Start position / bit position"),
    (r"\b(period|cycle|cycletime|rate|frequency)\b", "Cycle time / timing"),
    (r"\b(length|len|size|width|bits?|bytes?|dlc)\b", "Size / length (bits or bytes)"),
    (r"\b(can id|msg id|message id|frame id|arbitration)\b", "Bus message / frame identifier"),
    (r"\b(id|identifier|key|no|nr|number|index|idx)\b", "Unique identifier / index of the entry"),
    (r"\b(name|short.?name|label|signal|parameter|param|variable)\b", "Name of the item being described"),
    (r"\b(desc|description|comment|remark|note|notes|text)\b", "Free-text description or remark"),
    (r"\b(date|time|timestamp|created|modified|updated)\b", "Date / time information"),
    (r"\b(unit|units)\b", "Physical / engineering unit"),
    (r"\b(min|minimum|lower)\b", "Lower limit / minimum allowed value"),
    (r"\b(max|maximum|upper)\b", "Upper limit / maximum allowed value"),
    (r"\b(init|initial|default)\b", "Initial / default value"),
    (r"\b(factor|scale|scaling|resolution|gain)\b", "Scaling factor used for conversion"),
    (r"\b(offset)\b", "Offset applied in conversion"),
    (r"\b(type|datatype|data type|kind|category|class)\b", "Data type or category"),
    (r"\b(status|state)\b", "Status / state of the entry"),
    (r"\b(owner|author|responsible|assignee)\b", "Responsible person / owner"),
    (r"\b(version|rev|revision)\b", "Version / revision"),
    (r"\b(value|val|amount|qty|quantity|price|cost|total)\b", "Numeric value / quantity"),
    (r"\b(address|addr)\b", "Memory / bus address"),
    (r"\b(ecu|node|sender|receiver|tx|rx)\b", "Sending / receiving node (ECU)"),
    (r"\b(can|lin|flexray|ethernet|bus|channel|frame|pdu|message|msg)\b", "Communication bus / frame related"),
    (r"\b(priority|prio|severity|asil)\b", "Priority / safety or severity level"),
]

_CRITICAL_COL = re.compile(r"(id|length|len|size|start|pos|bit|offset|factor|init|min|max|address|addr|"
                           r"type|dlc|cycle|period|asil|byte|endian|order)", re.I)


def normalize_header(h: str) -> str:
    h = h.lower()
    h = re.sub(r"[\s_\-./()\[\]:#]+", " ", h)
    return " ".join(h.split())


def guess_meaning(header: str, samples: Iterable[str] = ()) -> str:
    n = normalize_header(header)
    for pat, meaning in _MEANING_HINTS:
        if re.search(pat, n):
            return meaning
    samples = [s for s in samples if s][:20]
    if samples and all(_to_number(s) is not None for s in samples):
        return "Numeric value"
    if samples and all(re.match(r"\d{4}-\d{2}-\d{2}", s) for s in samples):
        return "Date"
    return "Descriptive attribute"


def _to_number(s: str) -> Optional[float]:
    s = s.strip().replace(",", "") if isinstance(s, str) else s
    if s == "" or s is None:
        return None
    try:
        if isinstance(s, str) and re.fullmatch(r"[+-]?0[xX][0-9a-fA-F]+", s):
            return float(int(s, 16))
        return float(s)
    except (TypeError, ValueError):
        return None


def values_equal(a: str, b: str) -> bool:
    if a == b:
        return True
    na, nb = _to_number(a), _to_number(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= 1e-9 * max(1.0, abs(na), abs(nb))
    return False


def numeric_delta(a: str, b: str) -> str:
    na, nb = _to_number(a), _to_number(b)
    if na is None or nb is None:
        return ""
    d = nb - na
    txt = f"{d:+g}"
    if na != 0 and "x" not in (a + b).lower():
        txt += f", {d / abs(na) * 100:+.1f}%"
    return f" (Δ {txt})"


def short(v: str, n: int = 80) -> str:
    v = " ".join(str(v).split())
    return v if len(v) <= n else v[: n - 1] + "…"


def heuristic_column_mapping(ref: Table, tgt: Table) -> list[ColumnMapping]:
    """Map reference columns to target columns: exact → normalized → fuzzy → content."""
    maps: list[ColumnMapping] = []
    used: set[str] = set()
    tnorm = {normalize_header(h): h for h in tgt.headers}
    pending = []
    for h in ref.headers:
        meaning = guess_meaning(h, ref.column_values(h))
        if h in tgt.headers and h not in used:
            maps.append(ColumnMapping(ref.name, tgt.name, h, h, meaning, 1.0, "exact"))
            used.add(h)
        elif normalize_header(h) in tnorm and tnorm[normalize_header(h)] not in used:
            th = tnorm[normalize_header(h)]
            maps.append(ColumnMapping(ref.name, tgt.name, h, th, meaning, 0.95, "normalized",
                                      f"Header spelled differently: '{h}' vs '{th}'"))
            used.add(th)
        else:
            pending.append(h)
    for h in pending:
        meaning = guess_meaning(h, ref.column_values(h))
        best, score = None, 0.0
        for th in tgt.headers:
            if th in used:
                continue
            s = difflib.SequenceMatcher(None, normalize_header(h), normalize_header(th)).ratio()
            # content similarity helps with renamed columns
            rv, tv = set(ref.column_values(h)[:200]) - {""}, set(tgt.column_values(th)[:200]) - {""}
            if rv and tv:
                s = max(s, len(rv & tv) / len(rv | tv) * 0.9)
            if s > score:
                best, score = th, s
        if not best or score < 0.6:
            # semantic fallback: same inferred meaning, and that meaning is unique on both sides
            if meaning not in ("Descriptive attribute", "Numeric value"):
                same_r = [x for x in pending if guess_meaning(x, ref.column_values(x)) == meaning]
                same_t = [th for th in tgt.headers if th not in used
                          and guess_meaning(th, tgt.column_values(th)) == meaning]
                if len(same_r) == 1 and len(same_t) == 1:
                    maps.append(ColumnMapping(ref.name, tgt.name, h, same_t[0], meaning, 0.6, "semantic",
                                              f"Same meaning ({meaning.lower()}): '{h}' ≈ '{same_t[0]}'"))
                    used.add(same_t[0])
                    continue
        if best and score >= 0.6:
            maps.append(ColumnMapping(ref.name, tgt.name, h, best, meaning, round(score, 2), "fuzzy",
                                      f"Probably renamed: '{h}' → '{best}'"))
            used.add(best)
        else:
            maps.append(ColumnMapping(ref.name, tgt.name, h, None, meaning, 0.0, "unmatched",
                                      "Column not found in target"))
    for th in tgt.headers:
        if th not in used:
            maps.append(ColumnMapping(ref.name, tgt.name, "", th, guess_meaning(th, tgt.column_values(th)),
                                      0.0, "new", "Column only present in target"))
    return maps


def match_tables(ref: ParsedDocument, tgt: ParsedDocument) -> list[tuple[Optional[Table], Optional[Table]]]:
    pairs: list[tuple[Optional[Table], Optional[Table]]] = []
    remaining = list(tgt.tables)
    for rt in ref.tables:
        hit = next((t for t in remaining if t.name == rt.name), None)
        if hit is None:
            def sim(t: Table) -> float:
                a, b = {normalize_header(x) for x in rt.headers}, {normalize_header(x) for x in t.headers}
                return len(a & b) / max(1, len(a | b))
            cands = sorted(remaining, key=sim, reverse=True)
            if cands and sim(cands[0]) >= 0.3:
                hit = cands[0]
            elif cands and len(ref.tables) == 1 and len(tgt.tables) == 1:
                hit = cands[0]
        if hit is not None:
            remaining.remove(hit)
        pairs.append((rt, hit))
    for t in remaining:
        pairs.append((None, t))
    return pairs


def choose_key_columns(ref: Table, tgt: Table, maps: list[ColumnMapping]) -> list[str]:
    mapped = [m for m in maps if m.ref_column and m.tgt_column]
    hint = re.compile(r"(id|key|name|signal|param|no|number|code|ident)", re.I)

    def unique(vals: list[str]) -> bool:
        vals = [v for v in vals]
        nonempty = [v for v in vals if v]
        return bool(vals) and len(nonempty) >= 0.9 * len(vals) and len(set(nonempty)) == len(nonempty)

    singles = [m for m in mapped if unique(ref.column_values(m.ref_column)) and unique(tgt.column_values(m.tgt_column))]
    singles.sort(key=lambda m: (0 if hint.search(m.ref_column) else 1, ref.headers.index(m.ref_column)))
    if singles:
        return [singles[0].ref_column]
    for i, a in enumerate(mapped):
        for b in mapped[i + 1:]:
            rk = list(zip(ref.column_values(a.ref_column), ref.column_values(b.ref_column)))
            tk = list(zip(tgt.column_values(a.tgt_column), tgt.column_values(b.tgt_column)))
            if len(set(rk)) == len(rk) and len(set(tk)) == len(tk) and rk:
                return [a.ref_column, b.ref_column]
    return []


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class DiffEngine:
    def __init__(self, result: CompareResult):
        self.r = result
        self._next = 1

    def add(self, **kw) -> DiffItem:
        it = DiffItem(id=self._next, **kw)
        self._next += 1
        self.r.items.append(it)
        return it

    # ------------------------------------------------------------------ tables
    def diff_tables(self, ai_mappings: Optional[dict[str, list[ColumnMapping]]] = None,
                    ai_keys: Optional[dict[str, list[str]]] = None):
        ref, tgt = self.r.reference, self.r.target
        for rt, tt in match_tables(ref, tgt):
            if rt is None:
                self.add(category="Structure", change_type="Added", location=tt.location, element=tt.name,
                         tgt_value=f"{len(tt.rows)} rows, columns: {', '.join(tt.headers)}",
                         description=f"Table/sheet '{tt.name}' exists only in the target file.", impact="Medium")
                continue
            if tt is None:
                self.add(category="Structure", change_type="Removed", location=rt.location, element=rt.name,
                         ref_value=f"{len(rt.rows)} rows, columns: {', '.join(rt.headers)}",
                         description=f"Table/sheet '{rt.name}' is missing in the target file.", impact="High")
                continue
            maps = (ai_mappings or {}).get(rt.name) or heuristic_column_mapping(rt, tt)
            for m in maps:
                m.table_tgt = tt.name
            self.r.mappings.extend(maps)
            keys = [k for k in (ai_keys or {}).get(rt.name, []) if k in rt.headers]
            if not keys or not self._keys_valid(rt, tt, keys, maps):
                keys = choose_key_columns(rt, tt, maps)
            self.r.key_columns[rt.name] = keys
            self._diff_columns(rt, tt, maps)
            self._diff_rows(rt, tt, maps, keys)

    @staticmethod
    def _keys_valid(rt: Table, tt: Table, keys: list[str], maps: list[ColumnMapping]) -> bool:
        m = {x.ref_column: x.tgt_column for x in maps if x.ref_column}
        if any(not m.get(k) for k in keys):
            return False
        rk = list(zip(*[rt.column_values(k) for k in keys]))
        tk = list(zip(*[tt.column_values(m[k]) for k in keys]))
        return len(set(rk)) == len(rk) and len(set(tk)) == len(tk)

    def _diff_columns(self, rt: Table, tt: Table, maps: list[ColumnMapping]):
        loc = rt.location if rt.name == tt.name else f"{rt.location} ↔ {tt.location}"
        for m in maps:
            if m.ref_column and not m.tgt_column:
                self.add(category="Structure", change_type="Removed", location=loc, element=f"Column '{m.ref_column}'",
                         ref_value=m.ref_column, description=f"Column '{m.ref_column}' ({m.meaning.lower()}) "
                         f"is not present in the target.", impact="High")
            elif not m.ref_column and m.tgt_column:
                self.add(category="Structure", change_type="Added", location=loc, element=f"Column '{m.tgt_column}'",
                         tgt_value=m.tgt_column, description=f"New column '{m.tgt_column}' "
                         f"({m.meaning.lower()}) added in the target.", impact="Medium")
            elif m.ref_column != m.tgt_column:
                self.add(category="Structure", change_type="Renamed", location=loc, element=f"Column '{m.ref_column}'",
                         ref_value=m.ref_column, tgt_value=m.tgt_column,
                         description=f"Column header renamed from '{m.ref_column}' to '{m.tgt_column}' "
                         f"(same meaning: {m.meaning.lower()}; match {m.method}, confidence {m.confidence:.0%}).",
                         impact="Low")

    def _diff_rows(self, rt: Table, tt: Table, maps: list[ColumnMapping], keys: list[str]):
        pairs = [(m.ref_column, m.tgt_column, rt.headers.index(m.ref_column), tt.headers.index(m.tgt_column), m)
                 for m in maps if m.ref_column and m.tgt_column]
        cmap = {p[0]: p for p in pairs}
        loc = rt.location

        def keystr_ref(row):
            return " / ".join(f"{k}={row[rt.headers.index(k)]}" for k in keys) if keys else ""

        def rowtext(row, idx_list, headers):
            return "; ".join(f"{headers[i]}={row[i]}" for i in idx_list if i < len(row) and row[i] != "")

        matched: list[tuple[int, int]] = []
        added_t: list[int] = []
        removed_r: list[int] = []
        if keys:
            rk = {tuple(r[rt.headers.index(k)] for k in keys): i for i, r in enumerate(rt.rows)}
            tk = {tuple(r[cmap[k][3]] for k in keys): i for i, r in enumerate(tt.rows)}
            for k, i in rk.items():
                if k in tk:
                    matched.append((i, tk[k]))
                else:
                    removed_r.append(i)
            added_t = [j for k, j in tk.items() if k not in rk]
        else:
            ra = ["\x1f".join(r[p[2]] for p in pairs) for r in rt.rows]
            ta = ["\x1f".join(r[p[3]] if p[3] < len(r) else "" for p in pairs) for r in tt.rows]
            sm = difflib.SequenceMatcher(None, ra, ta, autojunk=False)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    matched += list(zip(range(i1, i2), range(j1, j2)))
                elif tag == "replace":
                    n = min(i2 - i1, j2 - j1)
                    matched += list(zip(range(i1, i1 + n), range(j1, j1 + n)))
                    removed_r += list(range(i1 + n, i2))
                    added_t += list(range(j1 + n, j2))
                elif tag == "delete":
                    removed_r += list(range(i1, i2))
                elif tag == "insert":
                    added_t += list(range(j1, j2))

        for i, j in matched:
            r_row, t_row = rt.rows[i], tt.rows[j]
            ident = keystr_ref(r_row) or f"row {i + 1} (target row {j + 1})"
            for rc, tc, ri, ti, m in pairs:
                a = r_row[ri] if ri < len(r_row) else ""
                b = t_row[ti] if ti < len(t_row) else ""
                if values_equal(a, b):
                    continue
                if a.strip().lower() == b.strip().lower() or " ".join(a.split()) == " ".join(b.split()):
                    impact, what = "Info", "formatting/case only"
                elif a == "":
                    impact, what = ("Medium", "value filled in")
                elif b == "":
                    impact, what = ("High" if _CRITICAL_COL.search(rc) else "Medium", "value cleared")
                else:
                    impact = "High" if (_CRITICAL_COL.search(rc) or rc in keys) else "Medium"
                    what = "value changed"
                self.add(category="Table", change_type="Modified", location=f"{loc} · row {i + 2}",
                         element=f"{ident} → {rc}", ref_value=a, tgt_value=b,
                         description=f"{rc} ({m.meaning.lower()}) for {ident}: {what} from "
                         f"'{short(a)}' to '{short(b)}'{numeric_delta(a, b)}.", impact=impact)
        r_idx = [p[2] for p in pairs] + [k for k in range(len(rt.headers)) if k not in [p[2] for p in pairs]]
        t_idx = list(range(len(tt.headers)))
        for i in removed_r:
            row = rt.rows[i]
            ident = keystr_ref(row) or f"row {i + 1}"
            self.add(category="Table", change_type="Removed", location=f"{loc} · row {i + 2}", element=ident,
                     ref_value=rowtext(row, r_idx, rt.headers),
                     description=f"Entry {ident} exists in the reference but was removed from the target.",
                     impact="High")
        for j in added_t:
            row = tt.rows[j]
            ident = (" / ".join(f"{k}={row[cmap[k][3]]}" for k in keys) if keys else f"target row {j + 1}")
            self.add(category="Table", change_type="Added", location=f"{tt.location} · row {j + 2}", element=ident,
                     tgt_value=rowtext(row, t_idx, tt.headers),
                     description=f"New entry {ident} added in the target.", impact="Medium")

    # ------------------------------------------------------------------ text
    def diff_text(self, ref_blocks: list[TextBlock], tgt_blocks: list[TextBlock], category: str = "Text"):
        a = [" ".join(b.text.split()) for b in ref_blocks]
        b = [" ".join(t.text.split()) for t in tgt_blocks]
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            if tag == "replace":
                ri, tj = list(range(i1, i2)), list(range(j1, j2))
                pairs = self._pair_similar(a, b, ri, tj)
                paired_r = {p[0] for p in pairs}
                paired_t = {p[1] for p in pairs}
                for x, y in pairs:
                    self.add(category=category, change_type="Modified",
                             location=f"{ref_blocks[x].location} ↔ {tgt_blocks[y].location}",
                             element=short(ref_blocks[x].text, 60), ref_value=ref_blocks[x].text,
                             tgt_value=tgt_blocks[y].text, description=describe_text_change(a[x], b[y]),
                             impact=_text_impact(a[x], b[y]))
                for x in ri:
                    if x not in paired_r:
                        self._text_removed(ref_blocks[x], category)
                for y in tj:
                    if y not in paired_t:
                        self._text_added(tgt_blocks[y], category)
            elif tag == "delete":
                for x in range(i1, i2):
                    self._text_removed(ref_blocks[x], category)
            elif tag == "insert":
                for y in range(j1, j2):
                    self._text_added(tgt_blocks[y], category)

    @staticmethod
    def _pair_similar(a, b, ri, tj):
        cands = []
        for x in ri:
            for y in tj:
                s = difflib.SequenceMatcher(None, a[x], b[y]).ratio()
                if s >= 0.5:
                    cands.append((s, x, y))
        cands.sort(reverse=True)
        used_x, used_y, out = set(), set(), []
        for s, x, y in cands:
            if x not in used_x and y not in used_y:
                out.append((x, y))
                used_x.add(x)
                used_y.add(y)
        return sorted(out)

    def _text_removed(self, blk: TextBlock, category: str):
        self.add(category=category, change_type="Removed", location=blk.location, element=short(blk.text, 60),
                 ref_value=blk.text, description=f"Text removed: “{short(blk.text, 120)}”.",
                 impact="Medium" if blk.style.lower().startswith("heading") else "Low")

    def _text_added(self, blk: TextBlock, category: str):
        self.add(category=category, change_type="Added", location=blk.location, element=short(blk.text, 60),
                 tgt_value=blk.text, description=f"Text added: “{short(blk.text, 120)}”.",
                 impact="Medium" if blk.style.lower().startswith("heading") else "Low")

    # ------------------------------------------------------------------ code
    def diff_code(self, ref: CodeModel, tgt: CodeModel):
        from .parsers.code import strip_comments_and_strings
        rs, ts = ref.by_key(), tgt.by_key()
        removed = [k for k in rs if k not in ts]
        added = [k for k in ts if k not in rs]
        # rename detection
        renamed = []
        for rk in list(removed):
            r = rs[rk]
            best, score = None, 0.0
            for tk in added:
                t = ts[tk]
                if t.kind != r.kind or r.kind in ("include",):
                    continue
                rb = _norm_code(strip_comments_and_strings(r.body)).replace(r.name, "§")
                tb = _norm_code(strip_comments_and_strings(t.body)).replace(t.name, "§")
                s = difflib.SequenceMatcher(None, rb, tb).ratio()
                if s > score:
                    best, score = tk, s
            if best and score >= 0.9 and len(r.body) > 20:
                renamed.append((rk, best, score))
                removed.remove(rk)
                added.remove(best)
        for rk, tk, sc in renamed:
            r, t = rs[rk], ts[tk]
            self.add(category="Code", change_type="Renamed", location=f"Line {r.line} → {t.line}",
                     element=f"{r.kind} {r.name} → {t.name}", ref_value=r.signature, tgt_value=t.signature,
                     description=f"{r.kind.capitalize()} '{r.name}' appears to be renamed to '{t.name}' "
                     f"({sc:.0%} identical implementation). All callers must use the new name.", impact="High")
        for k in removed:
            s = rs[k]
            self.add(category="Code", change_type="Removed", location=f"Line {s.line}", element=f"{s.kind} {s.name}",
                     ref_value=s.signature if s.kind != "macro" else f"{s.signature} {s.body}",
                     description=f"{s.kind.capitalize()} '{s.name}' was removed.",
                     impact=_code_impact(s.kind, "Removed"), details=s.body if s.kind != "macro" else "")
        for k in added:
            s = ts[k]
            self.add(category="Code", change_type="Added", location=f"Line {s.line}", element=f"{s.kind} {s.name}",
                     tgt_value=s.signature if s.kind != "macro" else f"{s.signature} {s.body}",
                     description=f"New {s.kind} '{s.name}' was added.",
                     impact=_code_impact(s.kind, "Added"), details=s.body if s.kind != "macro" else "")
        for k in rs:
            if k not in ts:
                continue
            r, t = rs[k], ts[k]
            if r.kind == "macro":
                if r.signature != t.signature or _norm_code(r.body) != _norm_code(t.body):
                    self.add(category="Code", change_type="Modified", location=f"Line {r.line} → {t.line}",
                             element=f"macro {r.name}", ref_value=f"{r.signature} {r.body}".strip(),
                             tgt_value=f"{t.signature} {t.body}".strip(),
                             description=f"Macro '{r.name}' changed from '{short(r.body)}' to '{short(t.body)}'"
                             f"{numeric_delta(r.body, t.body)}. Every user of this macro is affected.",
                             impact="High")
                continue
            if r.body == t.body:
                continue
            sig_changed = _norm_code(r.signature) != _norm_code(t.signature)
            rb_clean = _norm_code(strip_comments_and_strings(r.body))
            tb_clean = _norm_code(strip_comments_and_strings(t.body))
            hunk = unified_hunk(r.body, t.body, r.line, t.line)
            body_note = ""
            if sig_changed:
                rbody = rb_clean.replace(_norm_code(strip_comments_and_strings(r.signature)), "")
                tbody = tb_clean.replace(_norm_code(strip_comments_and_strings(t.signature)), "")
                if rbody != tbody and r.kind not in ("prototype",):
                    ra, rr = _count_changes(r.body, t.body)
                    body_note = f" The implementation also changed (+{ra} / −{rr} lines)."
                self.add(category="Code", change_type="Modified", location=f"Line {r.line} → {t.line}",
                         element=f"{r.kind} {r.name} (signature)", ref_value=r.signature, tgt_value=t.signature,
                         description=f"Signature/declaration of {r.kind} '{r.name}' changed. This is an interface "
                         f"change – callers and dependent modules must be checked." + body_note, impact="High",
                         details=hunk)
            elif rb_clean == tb_clean:
                self.add(category="Code", change_type="Modified", location=f"Line {r.line} → {t.line}",
                         element=f"{r.kind} {r.name}", ref_value="(comments/whitespace)", tgt_value="(comments/whitespace)",
                         description=f"Only comments or formatting changed in {r.kind} '{r.name}' – no functional impact.",
                         impact="Info", details=hunk)
            else:
                ra, rr = _count_changes(r.body, t.body)
                self.add(category="Code", change_type="Modified", location=f"Line {r.line} → {t.line}",
                         element=f"{r.kind} {r.name}", ref_value=short(r.signature, 120), tgt_value=short(t.signature, 120),
                         description=f"Implementation of {r.kind} '{r.name}' changed (+{ra} / −{rr} lines).",
                         impact="High" if r.kind.startswith(("struct", "typedef", "union", "enum", "class")) else "Medium",
                         details=hunk)

    # ------------------------------------------------------------------ arxml
    def diff_arxml(self, ref: ArxmlModel, tgt: ArxmlModel):
        rp, tp = ref.by_path(), tgt.by_path()
        if ref.autosar_version and tgt.autosar_version and ref.autosar_version != tgt.autosar_version:
            self.add(category="ARXML", change_type="Modified", location="AUTOSAR root", element="AUTOSAR schema",
                     ref_value=ref.autosar_version, tgt_value=tgt.autosar_version,
                     description="AUTOSAR schema version changed – check tool compatibility.", impact="High")
        removed = [p for p in rp if p not in tp]
        added = [p for p in tp if p not in rp]
        # rename: same parent, same tag, identical properties
        for p in list(removed):
            e = rp[p]
            parent = p.rsplit("/", 1)[0]
            for q in added:
                f = tp[q]
                if f.tag == e.tag and q.rsplit("/", 1)[0] == parent and f.properties == e.properties and e.properties:
                    self.add(category="ARXML", change_type="Renamed", location=f"{e.tag} (line {e.line} → {f.line})",
                             element=p, ref_value=p.rsplit("/", 1)[-1], tgt_value=q.rsplit("/", 1)[-1],
                             description=f"{e.tag} '{p.rsplit('/', 1)[-1]}' renamed to '{q.rsplit('/', 1)[-1]}' "
                             f"(content unchanged). References pointing to the old path will break.", impact="High")
                    removed.remove(p)
                    added.remove(q)
                    break
        removed_set = set(removed)
        added_set = set(added)
        for p in removed:
            if p.rsplit("/", 1)[0] in removed_set:
                continue                    # parent already reported
            e = rp[p]
            n_children = sum(1 for x in removed if x.startswith(p + "/"))
            extra = f" (including {n_children} nested element(s))" if n_children else ""
            self.add(category="ARXML", change_type="Removed", location=f"{e.tag} (line {e.line})", element=p,
                     ref_value=_props_preview(e.properties),
                     description=f"{e.tag} '{p.rsplit('/', 1)[-1]}' was removed{extra}.", impact="High")
        for p in added:
            if p.rsplit("/", 1)[0] in added_set:
                continue
            e = tp[p]
            n_children = sum(1 for x in added if x.startswith(p + "/"))
            extra = f" (including {n_children} nested element(s))" if n_children else ""
            self.add(category="ARXML", change_type="Added", location=f"{e.tag} (line {e.line})", element=p,
                     tgt_value=_props_preview(e.properties),
                     description=f"New {e.tag} '{p.rsplit('/', 1)[-1]}' added{extra}.", impact="Medium")
        for p, e in rp.items():
            f = tp.get(p)
            if f is None:
                continue
            if e.tag != f.tag:
                self.add(category="ARXML", change_type="Modified", location=f"line {e.line} → {f.line}", element=p,
                         ref_value=e.tag, tgt_value=f.tag,
                         description=f"Element type of '{p}' changed from {e.tag} to {f.tag}.", impact="High")
            keys = list(dict.fromkeys(list(e.properties) + list(f.properties)))
            for k in keys:
                a, b = e.properties.get(k), f.properties.get(k)
                if a == b or (a is not None and b is not None and values_equal(a, b)):
                    continue
                prop = "/".join(k.replace("/@", " @").split("/")[-2:])
                if a is None:
                    ct, desc = "Added", f"Property {prop} added to {e.tag} '{p.rsplit('/', 1)[-1]}' with value '{short(b)}'."
                elif b is None:
                    ct, desc = "Removed", f"Property {prop} removed from {e.tag} '{p.rsplit('/', 1)[-1]}' (was '{short(a)}')."
                else:
                    ct = "Modified"
                    desc = (f"{prop} of {e.tag} '{p.rsplit('/', 1)[-1]}' changed from '{short(a)}' to "
                            f"'{short(b)}'{numeric_delta(a, b)}.")
                self.add(category="ARXML", change_type=ct, location=f"{e.tag} (line {e.line} → {f.line})",
                         element=f"{p} :: {k}", ref_value=a or "", tgt_value=b or "", description=desc,
                         impact=_arxml_impact(k))

    # ------------------------------------------------------------------ side by side
    def build_side_by_side(self, a_lines: list[str], b_lines: list[str], context: int = 3, limit: int = 4000):
        sm = difflib.SequenceMatcher(None, [x.rstrip() for x in a_lines], [x.rstrip() for x in b_lines],
                                     autojunk=False)
        rows: list[SideBySideRow] = []
        for group in sm.get_grouped_opcodes(context):
            if rows:
                rows.append(SideBySideRow("skip", None, "", None, ""))
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    for k in range(i2 - i1):
                        rows.append(SideBySideRow("equal", i1 + k + 1, a_lines[i1 + k], j1 + k + 1, b_lines[j1 + k]))
                else:
                    n = max(i2 - i1, j2 - j1)
                    for k in range(n):
                        ai = i1 + k if i1 + k < i2 else None
                        bj = j1 + k if j1 + k < j2 else None
                        t = tag if (ai is not None and bj is not None) else ("delete" if bj is None else "insert")
                        rows.append(SideBySideRow(t, ai + 1 if ai is not None else None,
                                                  a_lines[ai] if ai is not None else "",
                                                  bj + 1 if bj is not None else None,
                                                  b_lines[bj] if bj is not None else ""))
            if len(rows) > limit:
                rows.append(SideBySideRow("skip", None, "… output truncated …", None, ""))
                break
        self.r.side_by_side = rows


# --------------------------------------------------------------------------- #
# Small description helpers
# --------------------------------------------------------------------------- #
def _norm_code(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def unified_hunk(a: str, b: str, la: int, lb: int, max_lines: int = 80) -> str:
    lines = list(difflib.unified_diff(a.splitlines(), b.splitlines(), fromfile="reference", tofile="target",
                                      lineterm="", n=2))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"… {len(lines) - max_lines} more diff lines"]
    return "\n".join(lines)


def _count_changes(a: str, b: str) -> tuple[int, int]:
    add = rem = 0
    for line in difflib.ndiff(a.splitlines(), b.splitlines()):
        if line.startswith("+ "):
            add += 1
        elif line.startswith("- "):
            rem += 1
    return add, rem


def _code_impact(kind: str, change: str) -> str:
    if kind in ("include",):
        return "Low" if change == "Added" else "Medium"
    if kind in ("function", "prototype", "macro", "struct", "typedef struct", "union", "enum", "class",
                "typedef enum", "typedef", "global"):
        return "High" if change == "Removed" else "Medium"
    return "Low"


def _arxml_impact(prop: str) -> str:
    p = prop.upper()
    if any(x in p for x in ("DESC", "LONG-NAME", "ADMIN-DATA", "INTRODUCTION", "ANNOTATION", "L-2", "L-4", "L-5", "UUID")):
        return "Low"
    if "REF" in p or "@DEST" in p:
        return "High"
    if any(x in p for x in ("LENGTH", "POSITION", "INIT", "OFFSET", "ID", "BAUDRATE", "TIME", "PERIOD",
                            "BYTE-ORDER", "LOWER-LIMIT", "UPPER-LIMIT", "COMPU", "CATEGORY", "BASE-TYPE", "SIZE")):
        return "High"
    return "Medium"


def _props_preview(props: dict[str, str], n: int = 6) -> str:
    items = [f"{k}={short(v, 40)}" for k, v in props.items() if v and not k.startswith("ADMIN")][:n]
    more = len(props) - len(items)
    return "; ".join(items) + (f"; … (+{more})" if more > 0 else "")


def describe_text_change(a: str, b: str) -> str:
    aw, bw = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, aw, bw)
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            parts.append(f"“{short(' '.join(aw[i1:i2]), 50)}” → “{short(' '.join(bw[j1:j2]), 50)}”")
        elif tag == "delete":
            parts.append(f"removed “{short(' '.join(aw[i1:i2]), 50)}”")
        elif tag == "insert":
            parts.append(f"added “{short(' '.join(bw[j1:j2]), 50)}”")
    if not parts:
        return "Whitespace/formatting changed."
    txt = "; ".join(parts[:4]) + (f"; and {len(parts) - 4} more edit(s)" if len(parts) > 4 else "")
    return f"Text reworded: {txt}."


def _text_impact(a: str, b: str) -> str:
    if a.lower() == b.lower():
        return "Info"
    na, nb = re.findall(r"\d+(?:\.\d+)?", a), re.findall(r"\d+(?:\.\d+)?", b)
    neg = re.compile(r"\b(not|no|never|shall|must|should|may)\b", re.I)
    if na != nb or [m.lower() for m in neg.findall(a)] != [m.lower() for m in neg.findall(b)]:
        return "High"
    return "Low"
