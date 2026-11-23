"""Claude-powered comparison agent.

The agent works in three phases:

1. **Understand & map columns** (agentic, tool use) – reads the reference file's
   column headings, profiles their values to infer what each column *means*,
   then finds the matching column in the target file (even if renamed or moved)
   and chooses the key column(s) that identify a row.
2. **Explain differences** (batched structured calls) – rewrites every detected
   difference as a precise, human-readable description with an impact rating.
3. **Summarize** (agentic, tool use) – investigates the diff (statistics,
   individual items, code symbols, ARXML elements) and writes an executive
   summary with key findings and an overall risk rating.

The deterministic DiffEngine always does the actual comparison, so the AI can
never invent or hide a difference – it only adds understanding.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

from .diff_engine import guess_meaning, heuristic_column_mapping, match_tables, short
from .models import ColumnMapping, CompareResult, DiffItem, ParsedDocument, Table

DEFAULT_MODEL = "claude-opus-5-5"
MODEL_CHOICES = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"]
# Models that accept the server-side refusal fallback parameter.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-fable-5-2", "claude-fable-5-1", "claude-opus-5", "claude-sonnet-5-5"}
_EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max"]
_IMPACTS = ["High", "Medium", "Low", "Info"]

LogFn = Callable[[str], None]


class AgentError(RuntimeError):
    pass


@dataclass
class AgentConfig:
    enabled: bool = True
    api_key: str = ""
    model: str = DEFAULT_MODEL
    effort: str = "medium"
    max_ai_items: int = 400       # differences described by the AI (rest keep rule-based text)
    batch_size: int = 40
    workers: int = 4
    max_turns: int = 14


SYSTEM_PROMPT = """You are CompareAgent, an expert reviewer embedded in a file comparison tool used by \
automotive / embedded software engineers. You compare a REFERENCE file (the baseline) with a TARGET file \
(the new version). Supported inputs include AUTOSAR ARXML, C/C++ sources and headers, Excel/CSV sheets, \
Word documents, PDFs and plain-text notes.

A deterministic diff engine has already parsed both files. You get read-only tools to inspect the parsed \
content and the detected differences. Use them to ground every statement – never invent values, rows, \
symbols or paths that the tools did not show you. Be concrete: name the column, signal, function, \
element or paragraph, quote old and new values, and explain the practical consequence for an engineer \
(interface change, timing change, memory layout, safety, documentation only, ...). Keep wording plain \
and short; no marketing language."""


# --------------------------------------------------------------------------- #
# JSON schemas for structured outputs
# --------------------------------------------------------------------------- #
_MAPPING_SCHEMA = {
    "type": "object",
    "properties": {
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref_table": {"type": "string"},
                    "tgt_table": {"type": "string"},
                    "key_columns": {"type": "array", "items": {"type": "string"}},
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ref_column": {"type": "string"},
                                "meaning": {"type": "string"},
                                "tgt_column": {"type": "string", "description": "Empty string if no match"},
                                "confidence": {"type": "number"},
                                "reasoning": {"type": "string"},
                            },
                            "required": ["ref_column", "meaning", "tgt_column", "confidence", "reasoning"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["ref_table", "tgt_table", "key_columns", "columns"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["tables", "notes"],
    "additionalProperties": False,
}

_DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "description": {"type": "string"},
                    "impact": {"type": "string", "enum": _IMPACTS},
                },
                "required": ["id", "description", "impact"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "overall_risk": {"type": "string", "enum": ["High", "Medium", "Low", "None"]},
        "key_findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["executive_summary", "overall_risk", "key_findings"],
    "additionalProperties": False,
}


def _tool(name: str, description: str, props: dict) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {"type": "object", "properties": props, "required": list(props),
                         "additionalProperties": False},
    }


_SIDE = {"type": "string", "enum": ["reference", "target"]}


class CompareAgent:
    def __init__(self, cfg: AgentConfig, log: LogFn = print):
        self.cfg = cfg
        self.log = log
        self._client = None

    # ------------------------------------------------------------------ setup
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise AgentError("The 'anthropic' package is not installed (pip install anthropic).") from exc
            kwargs = {"max_retries": 3}
            if self.cfg.api_key:
                kwargs["api_key"] = self.cfg.api_key
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def ready(self) -> tuple[bool, str]:
        if not self.cfg.enabled:
            return False, "AI agent disabled in settings"
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "anthropic package not installed"
        if not (self.cfg.api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.path.isdir(os.path.expanduser("~/.config/anthropic"))):
            return False, "no Anthropic API key configured"
        return True, ""

    # ------------------------------------------------------------------ core loop
    def _create(self, **kw):
        import anthropic
        params = dict(model=self.cfg.model, max_tokens=16000, system=SYSTEM_PROMPT,
                      cache_control={"type": "ephemeral"}, **kw)
        if self.cfg.model in _FALLBACK_MODELS:
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        try:
            return self.client().beta.messages.create(**params)
        except anthropic.AuthenticationError as exc:
            raise AgentError("Anthropic authentication failed – check the API key.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise AgentError(f"Permission denied by the Anthropic API: {exc.message}") from exc
        except anthropic.NotFoundError as exc:
            raise AgentError(f"Model '{self.cfg.model}' not available: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise AgentError("Rate limited by the Anthropic API – try again later.") from exc
        except anthropic.BadRequestError as exc:
            raise AgentError(f"Bad request: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise AgentError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentError("Cannot reach the Anthropic API – check the network / proxy.") from exc

    def run_agent(self, task: str, tools: list[dict], handlers: dict[str, Callable[..., object]],
                  schema: dict, effort: Optional[str] = None, label: str = "agent") -> dict:
        """Generic agent loop: Claude calls our read-only tools until it can answer in `schema`."""
        messages: list[dict] = [{"role": "user", "content": task}]
        output_config = {"effort": effort or self.cfg.effort, "format": {"type": "json_schema", "schema": schema}}
        for turn in range(self.cfg.max_turns):
            kw = dict(messages=messages, output_config=output_config)
            if tools:
                kw["tools"] = tools
            resp = self._create(**kw)
            if resp.stop_reason == "refusal":
                raise AgentError(f"{label}: the model declined the request.")
            if resp.stop_reason == "max_tokens":
                raise AgentError(f"{label}: response hit max_tokens.")
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "pause_turn":
                continue
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason == "tool_use" and tool_uses:
                for b in resp.content:
                    if b.type == "text" and b.text.strip():
                        self.log(f"   💭 {short(b.text, 160)}")
                results = []
                for tu in tool_uses:
                    args = tu.input if isinstance(tu.input, dict) else {}
                    self.log(f"   🔧 {tu.name}({', '.join(f'{k}={short(str(v), 40)}' for k, v in args.items())})")
                    fn = handlers.get(tu.name)
                    try:
                        if fn is None:
                            raise KeyError(f"unknown tool {tu.name}")
                        out = fn(**args)
                        content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
                        results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content[:60000]})
                    except Exception as exc:  # report tool errors back to the model
                        results.append({"type": "tool_result", "tool_use_id": tu.id,
                                        "content": f"Error: {exc}", "is_error": True})
                messages.append({"role": "user", "content": results})
                continue
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not text:
                raise AgentError(f"{label}: empty answer.")
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise AgentError(f"{label}: answer was not valid JSON.") from exc
        raise AgentError(f"{label}: no answer after {self.cfg.max_turns} turns.")

    # ================================================================== phase 1
    def map_columns(self, ref: ParsedDocument, tgt: ParsedDocument
                    ) -> tuple[dict[str, list[ColumnMapping]], dict[str, list[str]], str]:
        pairs = [(a, b) for a, b in match_tables(ref, tgt) if a is not None and b is not None]
        if not pairs:
            return {}, {}, ""
        docs = {"reference": ref, "target": tgt}

        def get_table(side: str, table: str) -> Table:
            t = docs[side].table(table)
            if t is None:
                raise ValueError(f"No table '{table}' in {side}. Available: {[x.name for x in docs[side].tables]}")
            return t

        def list_tables():
            return {
                "reference_file": ref.name, "target_file": tgt.name,
                "table_pairs_to_map": [{"ref_table": a.name, "tgt_table": b.name} for a, b in pairs],
                "reference_tables": [{"name": t.name, "rows": len(t.rows), "headers": t.headers} for t in ref.tables],
                "target_tables": [{"name": t.name, "rows": len(t.rows), "headers": t.headers} for t in tgt.tables],
            }

        def profile_column(side: str, table: str, column: str):
            t = get_table(side, table)
            if column not in t.headers:
                raise ValueError(f"No column '{column}' in {side}/{table}. Headers: {t.headers}")
            vals = t.column_values(column)
            ne = [v for v in vals if v]
            distinct = list(dict.fromkeys(ne))
            nums = 0
            for v in ne:
                try:
                    float(v.replace(",", ""))
                    nums += 1
                except ValueError:
                    pass
            return {"column": column, "rows": len(vals), "empty": len(vals) - len(ne), "distinct": len(distinct),
                    "unique": len(distinct) == len(ne) and len(ne) > 0,
                    "numeric_ratio": round(nums / len(ne), 2) if ne else 0,
                    "samples": [short(v, 60) for v in distinct[:12]]}

        def compare_column_values(ref_table: str, ref_column: str, tgt_table: str, tgt_column: str):
            a = set(get_table("reference", ref_table).column_values(ref_column)) - {""}
            b = set(get_table("target", tgt_table).column_values(tgt_column)) - {""}
            inter = a & b
            return {"value_overlap_jaccard": round(len(inter) / max(1, len(a | b)), 3),
                    "shared_examples": [short(v, 40) for v in list(inter)[:8]],
                    "only_reference_examples": [short(v, 40) for v in list(a - b)[:6]],
                    "only_target_examples": [short(v, 40) for v in list(b - a)[:6]]}

        tools = [
            _tool("list_tables", "List the tables/sheets of both files with their headers and row counts, "
                                 "and which table pairs must be mapped.", {}),
            _tool("profile_column", "Profile one column: emptiness, uniqueness, numeric ratio and sample values. "
                                    "Use it to understand what a column means.",
                  {"side": _SIDE, "table": {"type": "string"}, "column": {"type": "string"}}),
            _tool("compare_column_values", "Measure how much the values of a reference column overlap with a "
                                           "target column – strong evidence that a renamed column is the same.",
                  {"ref_table": {"type": "string"}, "ref_column": {"type": "string"},
                   "tgt_table": {"type": "string"}, "tgt_column": {"type": "string"}}),
        ]
        handlers = {"list_tables": list_tables, "profile_column": profile_column,
                    "compare_column_values": compare_column_values}
        task = (
            "PHASE 1 – understand and map columns.\n"
            "For every table pair to map: read each REFERENCE column heading, inspect its values where the heading "
            "is ambiguous, and state its meaning in one short sentence. Then find the TARGET column that holds the "
            "same information – exact name first, otherwise a renamed/re-ordered column with the same meaning and "
            "overlapping values. Use an empty tgt_column when the column was really removed. Never map two "
            "reference columns to the same target column. Finally pick key_columns: the reference column(s) whose "
            "values uniquely identify a row in BOTH files (e.g. signal name, ID); use an empty list if none.\n"
            "Start with list_tables. Return every reference column of every pair."
        )
        self.log("🤖 Agent phase 1: understanding reference columns and mapping them to the target…")
        data = self.run_agent(task, tools, handlers, _MAPPING_SCHEMA, label="column mapping")

        mappings: dict[str, list[ColumnMapping]] = {}
        keys: dict[str, list[str]] = {}
        by_ref = {t.get("ref_table"): t for t in data.get("tables", [])}
        for rt, tt in pairs:
            entry = by_ref.get(rt.name)
            fallback = {m.ref_column: m for m in heuristic_column_mapping(rt, tt) if m.ref_column}
            if not entry:
                continue
            ai_cols = {c["ref_column"]: c for c in entry.get("columns", []) if c.get("ref_column") in rt.headers}
            used: set[str] = set()
            out: list[ColumnMapping] = []
            for h in rt.headers:
                c = ai_cols.get(h)
                if c is not None:
                    tc = c.get("tgt_column") or None
                    if tc is not None and (tc not in tt.headers or tc in used):
                        tc = None
                    method = "exact" if tc == h else ("ai" if tc else "unmatched")
                    m = ColumnMapping(rt.name, tt.name, h, tc, c.get("meaning", "") or guess_meaning(h),
                                      float(c.get("confidence", 0.8) or 0.8), method, c.get("reasoning", ""))
                else:
                    m = fallback[h]
                    if m.tgt_column in used:
                        m.tgt_column, m.method = None, "unmatched"
                if m.tgt_column:
                    used.add(m.tgt_column)
                out.append(m)
            for th in tt.headers:
                if th not in used:
                    out.append(ColumnMapping(rt.name, tt.name, "", th, guess_meaning(th, tt.column_values(th)),
                                             0.0, "new", "Column only present in target"))
            mappings[rt.name] = out
            keys[rt.name] = [k for k in entry.get("key_columns", []) if k in rt.headers]
            self.log(f"   ✔ {rt.name}: {sum(1 for m in out if m.ref_column and m.tgt_column)} columns mapped, "
                     f"key = {keys[rt.name] or 'auto'}")
        return mappings, keys, data.get("notes", "")

    # ================================================================== phase 2
    def describe_items(self, result: CompareResult, progress: Optional[Callable[[int, int], None]] = None):
        prio = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}
        items = sorted(result.items, key=lambda i: (prio.get(i.impact, 9), i.id))[: self.cfg.max_ai_items]
        if not items:
            return
        meanings = [f"{m.ref_column or m.tgt_column}: {m.meaning}" for m in result.mappings][:80]
        ctx = (f"Reference file: {result.reference.name} ({result.reference.file_type})\n"
               f"Target file: {result.target.name} ({result.target.file_type})\n")
        if meanings:
            ctx += "Column meanings: " + "; ".join(meanings) + "\n"
        batches = [items[i:i + self.cfg.batch_size] for i in range(0, len(items), self.cfg.batch_size)]
        effort = _EFFORT_ORDER[min(_EFFORT_ORDER.index(self.cfg.effort) if self.cfg.effort in _EFFORT_ORDER else 1, 1)]
        by_id = {i.id: i for i in result.items}
        self.log(f"🤖 Agent phase 2: writing human-readable descriptions for {len(items)} difference(s) "
                 f"in {len(batches)} batch(es)…")

        def work(batch: list[DiffItem]) -> dict:
            payload = [{"id": it.id, "category": it.category, "change": it.change_type, "location": it.location,
                        "element": it.element, "reference_value": short(it.ref_value, 400),
                        "target_value": short(it.tgt_value, 400), "draft": it.description,
                        "draft_impact": it.impact, "code_diff": it.details[:1500] if it.details else ""}
                       for it in batch]
            task = (ctx + "PHASE 2 – explain each difference below for an engineer reading a review report.\n"
                    "For every id write 1–2 sentences: what changed (quote old → new values), and why it matters "
                    "(e.g. interface/ABI change, timing, scaling, memory layout, safety, documentation only). "
                    "Rate impact High/Medium/Low/Info: High = functional/interface/safety relevant, "
                    "Info = cosmetic only. Return every id exactly once.\n\n"
                    + json.dumps(payload, ensure_ascii=False))
            return self.run_agent(task, [], {}, _DESCRIBE_SCHEMA, effort=effort, label="describe")

        done = 0
        with ThreadPoolExecutor(max_workers=self.cfg.workers) as ex:
            futs = {ex.submit(work, b): b for b in batches}
            for fut in as_completed(futs):
                try:
                    data = fut.result()
                    for d in data.get("items", []):
                        it = by_id.get(d.get("id"))
                        if it and d.get("description"):
                            it.description = d["description"].strip()
                            if d.get("impact") in _IMPACTS:
                                it.impact = d["impact"]
                            it.ai_described = True
                except AgentError as exc:
                    self.log(f"   ⚠ batch failed, keeping rule-based descriptions: {exc}")
                done += 1
                if progress:
                    progress(done, len(batches))

    # ================================================================== phase 3
    def summarize(self, result: CompareResult):
        ref, tgt = result.reference, result.target
        docs = {"reference": ref, "target": tgt}

        def get_diff_statistics():
            stats: dict = {"total": len(result.items), "by_change": result.counts(), "by_category": {},
                           "by_impact": {}}
            for it in result.items:
                stats["by_category"][it.category] = stats["by_category"].get(it.category, 0) + 1
                stats["by_impact"][it.impact] = stats["by_impact"].get(it.impact, 0) + 1
            stats["files"] = {"reference": f"{ref.name} ({ref.file_type})", "target": f"{tgt.name} ({tgt.file_type})"}
            stats["key_columns"] = result.key_columns
            stats["column_mapping"] = [f"{m.ref_column or '∅'} → {m.tgt_column or '∅'} ({m.meaning})"
                                       for m in result.mappings][:60]
            return stats

        def get_diff_items(category: str, impact: str, offset: int, limit: int):
            sel = [it for it in result.items
                   if (category in ("", "any") or it.category == category)
                   and (impact in ("", "any") or it.impact == impact)]
            limit = max(1, min(limit, 80))
            return {"total_matching": len(sel), "items": [
                {"id": it.id, "category": it.category, "change": it.change_type, "impact": it.impact,
                 "location": it.location, "element": short(it.element, 120), "ref": short(it.ref_value, 160),
                 "tgt": short(it.tgt_value, 160), "description": short(it.description, 300)}
                for it in sel[offset:offset + limit]]}

        def get_code_symbol(side: str, name: str):
            code = docs[side].code
            if not code:
                return "This file is not C/C++ source."
            hits = [s for s in code.symbols if s.name == name]
            if not hits:
                return f"No symbol '{name}'."
            return [{"kind": s.kind, "line": s.line, "signature": s.signature, "body": s.body[:4000]} for s in hits]

        def get_arxml_element(side: str, path: str):
            ax = docs[side].arxml
            if not ax:
                return "This file is not ARXML."
            e = ax.by_path().get(path)
            if not e:
                cands = [p for p in ax.by_path() if p.endswith("/" + path.rsplit("/", 1)[-1])][:10]
                return f"No element '{path}'. Similar: {cands}"
            return {"path": e.path, "tag": e.tag, "line": e.line, "properties": dict(list(e.properties.items())[:150])}

        def search_document(side: str, query: str):
            q = query.lower()
            hits = [f"{b.location}: {short(b.text, 200)}" for b in docs[side].text_blocks if q in b.text.lower()]
            return {"matches": len(hits), "first": hits[:25]}

        tools = [
            _tool("get_diff_statistics", "Totals of differences by change type, category and impact, plus "
                                         "the column mapping and key columns.", {}),
            _tool("get_diff_items", "Page through detected differences. Use '' or 'any' for no filter. "
                                    "category: Table, Text, Code, ARXML, Structure. impact: High, Medium, Low, Info.",
                  {"category": {"type": "string"}, "impact": {"type": "string"},
                   "offset": {"type": "integer"}, "limit": {"type": "integer"}}),
            _tool("get_code_symbol", "Return the full source of a C/C++ symbol (function, macro, struct…).",
                  {"side": _SIDE, "name": {"type": "string"}}),
            _tool("get_arxml_element", "Return an ARXML element and its properties by SHORT-NAME path.",
                  {"side": _SIDE, "path": {"type": "string"}}),
            _tool("search_document", "Case-insensitive search for text in one of the files.",
                  {"side": _SIDE, "query": {"type": "string"}}),
        ]
        handlers = {"get_diff_statistics": get_diff_statistics, "get_diff_items": get_diff_items,
                    "get_code_symbol": get_code_symbol, "get_arxml_element": get_arxml_element,
                    "search_document": search_document}
        task = ("PHASE 3 – write the review summary.\n"
                "Investigate the differences with the tools (start with get_diff_statistics, then look at the "
                "High impact items and anything surprising). Then return: executive_summary (4–8 sentences, plain "
                "language: what kind of change this is overall and what a reviewer must look at), overall_risk, "
                "and 3–10 key_findings, each a concrete sentence naming the element and old → new values.")
        self.log("🤖 Agent phase 3: investigating the differences and writing the executive summary…")
        data = self.run_agent(task, tools, handlers, _SUMMARY_SCHEMA, label="summary")
        result.executive_summary = data.get("executive_summary", "").strip()
        result.overall_risk = data.get("overall_risk", "")
        result.key_findings = [k.strip() for k in data.get("key_findings", []) if k.strip()]
