"""High level pipeline: parse → (AI) understand → diff → (AI) explain → summarize."""
from __future__ import annotations

import time
from typing import Callable, Optional

from .ai_agent import AgentConfig, AgentError, CompareAgent
from .diff_engine import DiffEngine
from .models import CompareResult
from .parsers import parse_file

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, str], None]


def compare_files(ref_path: str, tgt_path: str, cfg: Optional[AgentConfig] = None,
                  log: LogFn = print, progress: Optional[ProgressFn] = None) -> CompareResult:
    cfg = cfg or AgentConfig()
    t0 = time.time()
    lines: list[str] = []

    def _log(msg: str):
        lines.append(msg)
        log(msg)

    def _prog(p: int, msg: str):
        if progress:
            progress(p, msg)

    _prog(3, "Reading reference file…")
    _log(f"📄 Reference: {ref_path}")
    ref = parse_file(ref_path)
    _log(f"   type={ref.file_type}, tables={len(ref.tables)}, text blocks={len(ref.text_blocks)}"
         + (f", code symbols={len(ref.code.symbols)}" if ref.code else "")
         + (f", ARXML elements={len(ref.arxml.elements)}" if ref.arxml else ""))
    _prog(8, "Reading target file…")
    _log(f"📄 Target:    {tgt_path}")
    tgt = parse_file(tgt_path)
    _log(f"   type={tgt.file_type}, tables={len(tgt.tables)}, text blocks={len(tgt.text_blocks)}"
         + (f", code symbols={len(tgt.code.symbols)}" if tgt.code else "")
         + (f", ARXML elements={len(tgt.arxml.elements)}" if tgt.arxml else ""))
    for w in ref.warnings:
        _log(f"⚠ reference: {w}")
    for w in tgt.warnings:
        _log(f"⚠ target: {w}")

    result = CompareResult(reference=ref, target=tgt, model=cfg.model)
    agent = CompareAgent(cfg, _log)
    ai_ok, why = agent.ready()
    if ai_ok:
        _log(f"🧠 AI agent active ({cfg.model}, effort {cfg.effort})")
    else:
        _log(f"ℹ AI agent not used: {why}. Using the built-in rule-based analysis.")
    engine = DiffEngine(result)

    # ---------------- tables -------------------------------------------------
    if ref.tables and tgt.tables:
        ai_maps, ai_keys = None, None
        if ai_ok:
            _prog(15, "AI agent: understanding columns…")
            try:
                ai_maps, ai_keys, notes = agent.map_columns(ref, tgt)
                result.ai_used = True
                if notes:
                    _log(f"   📝 {notes}")
            except AgentError as exc:
                _log(f"⚠ AI column mapping failed ({exc}); using heuristic mapping.")
        _prog(35, "Comparing tables…")
        engine.diff_tables(ai_maps, ai_keys)

    # ---------------- code / arxml / text -----------------------------------
    _prog(45, "Comparing content…")
    if ref.code and tgt.code:
        engine.diff_code(ref.code, tgt.code)
    elif ref.arxml and tgt.arxml:
        engine.diff_arxml(ref.arxml, tgt.arxml)
    elif ref.file_type in ("word", "pdf", "text") or tgt.file_type in ("word", "pdf", "text") \
            or (ref.text_blocks and tgt.text_blocks and not (ref.tables and tgt.tables)):
        if ref.text_blocks or tgt.text_blocks:
            engine.diff_text(ref.text_blocks, tgt.text_blocks)

    # side-by-side view
    a_lines = ref.raw_lines or [b.text for b in ref.text_blocks]
    b_lines = tgt.raw_lines or [b.text for b in tgt.text_blocks]
    if a_lines or b_lines:
        engine.build_side_by_side(a_lines, b_lines)
    _log(f"🔍 Diff engine found {len(result.items)} difference(s): "
         + ", ".join(f"{k} {v}" for k, v in result.counts().items() if v))

    # ---------------- AI explanations ---------------------------------------
    if ai_ok and result.items:
        _prog(55, "AI agent: describing differences…")
        try:
            agent.describe_items(result, progress=lambda d, n: _prog(55 + int(25 * d / max(1, n)),
                                                                      f"AI agent: describing ({d}/{n})…"))
            result.ai_used = True
        except AgentError as exc:
            _log(f"⚠ AI descriptions failed ({exc}).")
        _prog(82, "AI agent: writing summary…")
        try:
            agent.summarize(result)
            result.ai_used = True
        except AgentError as exc:
            _log(f"⚠ AI summary failed ({exc}).")
    if not result.executive_summary:
        rule_based_summary(result)

    result.elapsed_s = time.time() - t0
    _log(f"✅ Done in {result.elapsed_s:.1f}s")
    result.agent_log = lines
    _prog(100, "Done")
    return result


def rule_based_summary(result: CompareResult):
    items = result.items
    if not items:
        result.executive_summary = (f"No differences were found between '{result.reference.name}' and "
                                    f"'{result.target.name}'. The files are equivalent in content.")
        result.overall_risk = "None"
        result.key_findings = []
        return
    by_imp: dict[str, int] = {}
    by_cat: dict[str, int] = {}
    for it in items:
        by_imp[it.impact] = by_imp.get(it.impact, 0) + 1
        by_cat[it.category] = by_cat.get(it.category, 0) + 1
    c = result.counts()
    result.overall_risk = "High" if by_imp.get("High") else "Medium" if by_imp.get("Medium") else "Low"
    parts = [f"{len(items)} difference(s) found between '{result.reference.name}' (reference) and "
             f"'{result.target.name}' (target): {c['Added']} added, {c['Removed']} removed, "
             f"{c['Modified']} modified, {c['Renamed']} renamed."]
    parts.append("Areas affected: " + ", ".join(f"{k} ({v})" for k, v in sorted(by_cat.items(), key=lambda x: -x[1])) + ".")
    if by_imp.get("High"):
        parts.append(f"{by_imp['High']} change(s) are rated High impact and should be reviewed first.")
    renamed = [m for m in result.mappings if m.ref_column and m.tgt_column and m.ref_column != m.tgt_column]
    if renamed:
        parts.append(f"{len(renamed)} column(s) were matched despite a different heading.")
    result.executive_summary = " ".join(parts)
    prio = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}
    result.key_findings = [it.description for it in sorted(items, key=lambda i: (prio.get(i.impact, 9), i.id))[:8]]
