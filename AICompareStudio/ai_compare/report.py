"""HTML report generator – grey / black / gold theme, self-contained single file."""
from __future__ import annotations

import datetime as _dt
import difflib
import html
import re

from .models import CompareResult

_TOKEN = re.compile(r"(\s+|[^\w\s])")


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def intraline(a: str, b: str) -> tuple[str, str]:
    """Return (ref_html, tgt_html) with word-level changes highlighted."""
    ta = [t for t in _TOKEN.split(a) if t]
    tb = [t for t in _TOKEN.split(b) if t]
    if len(ta) * len(tb) > 250_000:
        return _e(a), _e(b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    oa, ob = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        sa, sb = "".join(ta[i1:i2]), "".join(tb[j1:j2])
        if tag == "equal":
            oa.append(_e(sa))
            ob.append(_e(sb))
        else:
            if sa:
                oa.append(f"<del>{_e(sa)}</del>")
            if sb:
                ob.append(f"<ins>{_e(sb)}</ins>")
    return "".join(oa), "".join(ob)


CSS = """
:root{--bg:#0d0d0f;--panel:#17171a;--panel2:#1f1f23;--line:#2c2c31;--text:#e6e6e6;--muted:#9a9aa2;
--gold:#d4af37;--gold2:#f3d27a;--golddim:#8a7426;--add:#3fae6a;--rem:#d9534f;--mod:#d4af37;--ren:#5b9bd5;
--high:#e0544e;--med:#e3a33b;--low:#6fa8dc;--info:#8d8d95}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
a{color:var(--gold2)}
.wrap{max-width:1500px;margin:0 auto;padding:24px 16px 60px}
header{border:1px solid var(--line);border-radius:14px;padding:22px 26px;
background:linear-gradient(135deg,#1b1b1f 0%,#111113 60%,#1d1a10 100%);box-shadow:0 0 0 1px #000 inset}
h1{margin:0;font-size:26px;letter-spacing:.5px;color:var(--gold)}
h1 small{color:var(--muted);font-weight:400;font-size:14px;margin-left:8px}
h2{color:var(--gold);font-size:18px;margin:34px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--golddim)}
.files{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px}
.file{background:var(--panel2);border:1px solid var(--line);border-left:3px solid var(--gold);border-radius:8px;padding:10px 14px;overflow-wrap:anywhere}
.file b{color:var(--gold2);display:block;font-size:12px;text-transform:uppercase;letter-spacing:1px}
.meta{color:var(--muted);font-size:12px;margin-top:10px}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;border:1px solid var(--line);background:#222}
.badge.ai{border-color:var(--gold);color:var(--gold2)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-top:18px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card .n{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}
.card .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:1px}
.c-total .n{color:var(--gold2)}.c-add .n{color:var(--add)}.c-rem .n{color:var(--rem)}.c-mod .n{color:var(--mod)}
.c-ren .n{color:var(--ren)}.c-high .n{color:var(--high)}
.summary{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.summary p{margin:0 0 10px}
.risk{font-weight:700}.risk.High{color:var(--high)}.risk.Medium{color:var(--med)}.risk.Low{color:var(--low)}.risk.None{color:var(--add)}
ul.find{margin:8px 0 0;padding-left:20px}ul.find li{margin:4px 0}ul.find li::marker{color:var(--gold)}
.tbl-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
table{border-collapse:collapse;width:100%}
th{position:sticky;top:0;background:#101012;color:var(--gold);text-align:left;font-weight:600;font-size:12px;
text-transform:uppercase;letter-spacing:.8px;padding:10px;border-bottom:2px solid var(--golddim);cursor:pointer;white-space:nowrap}
th:hover{color:var(--gold2)}
td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:nth-child(even) td{background:#141417}
tr:hover td{background:#1d1c18}
td.val{font-family:Consolas,"Cascadia Mono",Menlo,monospace;font-size:12.5px;max-width:330px;overflow-wrap:anywhere;white-space:pre-wrap}
td.loc{color:var(--muted);font-size:12.5px;max-width:240px;overflow-wrap:anywhere}
td.el{max-width:260px;overflow-wrap:anywhere;font-weight:600}
td.desc{min-width:280px;max-width:460px}
del{background:rgba(217,83,79,.25);color:#ffb3b0;text-decoration:line-through;border-radius:3px}
ins{background:rgba(63,174,106,.25);color:#a8f0c4;text-decoration:none;border-radius:3px}
.pill{display:inline-block;padding:1px 9px;border-radius:12px;font-size:11.5px;font-weight:700;white-space:nowrap}
.ct-Added{background:rgba(63,174,106,.15);color:var(--add);border:1px solid var(--add)}
.ct-Removed{background:rgba(217,83,79,.15);color:var(--rem);border:1px solid var(--rem)}
.ct-Modified{background:rgba(212,175,55,.12);color:var(--gold2);border:1px solid var(--gold)}
.ct-Renamed{background:rgba(91,155,213,.15);color:var(--ren);border:1px solid var(--ren)}
.im-High{color:#fff;background:var(--high)}.im-Medium{color:#111;background:var(--med)}
.im-Low{color:#111;background:var(--low)}.im-Info{color:#111;background:var(--info)}
.ai-dot{color:var(--gold);font-size:11px;margin-left:4px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.toolbar input{flex:1;min-width:220px;background:var(--panel2);border:1px solid var(--line);color:var(--text);
padding:8px 12px;border-radius:8px;outline:none}
.toolbar input:focus{border-color:var(--gold)}
.chip{background:var(--panel2);border:1px solid var(--line);color:var(--muted);padding:5px 12px;border-radius:20px;cursor:pointer;font-size:12.5px;user-select:none}
.chip.on{border-color:var(--gold);color:var(--gold2);background:#221f14}
details{margin-top:6px}summary{cursor:pointer;color:var(--gold2);font-size:12px}
pre.hunk{background:#0a0a0b;border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12px;overflow:auto;max-height:340px;margin:6px 0 0}
pre.hunk .a{color:#a8f0c4}pre.hunk .r{color:#ffb3b0}pre.hunk .h{color:var(--gold)}
.sbs td{font-family:Consolas,"Cascadia Mono",Menlo,monospace;font-size:12px;white-space:pre-wrap;padding:2px 8px;border:none}
.sbs td.no{color:#5d5d63;text-align:right;width:46px;user-select:none;background:#0f0f11}
.sbs tr.replace td.t{background:rgba(212,175,55,.09)}.sbs tr.delete td.a{background:rgba(217,83,79,.14)}
.sbs tr.insert td.b{background:rgba(63,174,106,.14)}.sbs tr.skip td{background:#101012;color:var(--gold);text-align:center}
.sbs td.a,.sbs td.b{width:47%;overflow-wrap:anywhere}
.log{background:#0a0a0b;border:1px solid var(--line);border-radius:10px;padding:12px;font-family:Consolas,monospace;font-size:12px;white-space:pre-wrap;color:#bdbdc4}
footer{margin-top:40px;color:var(--muted);font-size:12px;text-align:center}
footer b{color:var(--gold)}
.hidden{display:none}
@media (max-width:760px){.files{grid-template-columns:1fr}}
@media print{body{background:#fff;color:#000}header,.card,.summary,.tbl-wrap{background:#fff}.toolbar{display:none}}
"""

JS = """
(function(){
 const q=document.getElementById('q'),rows=[...document.querySelectorAll('#diffs tbody tr')];
 const state={impact:new Set(),change:new Set(),category:new Set()};
 function apply(){const s=(q.value||'').toLowerCase();let n=0;
  rows.forEach(r=>{let ok=(!s||r.textContent.toLowerCase().includes(s));
   for(const k in state){if(state[k].size&&!state[k].has(r.dataset[k]))ok=false;}
   r.classList.toggle('hidden',!ok);if(ok)n++;});
  document.getElementById('shown').textContent=n;}
 q&&q.addEventListener('input',apply);
 document.querySelectorAll('.chip').forEach(c=>c.addEventListener('click',()=>{
  const k=c.dataset.k,v=c.dataset.v;c.classList.toggle('on');
  state[k].has(v)?state[k].delete(v):state[k].add(v);apply();}));
 document.querySelectorAll('table.sortable th').forEach((th,i)=>th.addEventListener('click',()=>{
  const tb=th.closest('table').tBodies[0],rs=[...tb.rows],asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
  rs.sort((a,b)=>{const x=a.cells[i].dataset.s??a.cells[i].textContent,y=b.cells[i].dataset.s??b.cells[i].textContent;
   const nx=parseFloat(x),ny=parseFloat(y);
   const c=(!isNaN(nx)&&!isNaN(ny))?nx-ny:x.localeCompare(y);return asc?c:-c;});
  rs.forEach(r=>tb.appendChild(r));}));
})();
"""


def _hunk_html(h: str) -> str:
    out = []
    for line in h.splitlines():
        cls = "a" if line.startswith("+") and not line.startswith("+++") else \
              "r" if line.startswith("-") and not line.startswith("---") else \
              "h" if line.startswith("@@") else ""
        out.append(f'<span class="{cls}">{_e(line)}</span>' if cls else _e(line))
    return "\n".join(out)


def build_html(result: CompareResult) -> str:
    ref, tgt = result.reference, result.target
    c = result.counts()
    high = sum(1 for i in result.items if i.impact == "High")
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    ai_badge = (f'<span class="badge ai">🧠 AI agent · {_e(result.model)}</span>' if result.ai_used
                else '<span class="badge">Rule-based analysis</span>')
    P = []
    P.append(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Difference Report</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><h1>AI Compare Studio <small>Difference report</small></h1>
<div class="files"><div class="file"><b>Reference (baseline)</b>{_e(ref.path)}<br><span class="meta">{_e(ref.file_type.upper())}</span></div>
<div class="file"><b>Target (new)</b>{_e(tgt.path)}<br><span class="meta">{_e(tgt.file_type.upper())}</span></div></div>
<div class="meta">Generated {now} · {result.elapsed_s:.1f}s · {ai_badge}</div></header>
<div class="cards">
<div class="card c-total"><div class="n">{len(result.items)}</div><div class="l">Total differences</div></div>
<div class="card c-add"><div class="n">{c['Added']}</div><div class="l">Added</div></div>
<div class="card c-rem"><div class="n">{c['Removed']}</div><div class="l">Removed</div></div>
<div class="card c-mod"><div class="n">{c['Modified']}</div><div class="l">Modified</div></div>
<div class="card c-ren"><div class="n">{c['Renamed']}</div><div class="l">Renamed</div></div>
<div class="card c-high"><div class="n">{high}</div><div class="l">High impact</div></div>
</div>""")

    # ---- summary
    P.append('<h2>Executive summary</h2><div class="summary">')
    if result.overall_risk:
        P.append(f'<p>Overall risk: <span class="risk {_e(result.overall_risk)}">{_e(result.overall_risk)}</span></p>')
    for para in (result.executive_summary or "").split("\n"):
        if para.strip():
            P.append(f"<p>{_e(para)}</p>")
    if result.key_findings:
        P.append("<b style='color:var(--gold)'>Key findings</b><ul class='find'>")
        P += [f"<li>{_e(k)}</li>" for k in result.key_findings]
        P.append("</ul>")
    P.append("</div>")

    # ---- column understanding
    if result.mappings:
        P.append("<h2>Column understanding &amp; mapping</h2><div class='tbl-wrap'><table class='sortable'><thead><tr>"
                 "<th>Table / sheet</th><th>Reference column</th><th>Meaning (as understood)</th><th>Target column</th>"
                 "<th>Match</th><th>Confidence</th><th>Key</th><th>Note</th></tr></thead><tbody>")
        for m in result.mappings:
            is_key = m.ref_column in result.key_columns.get(m.table_ref, [])
            match = {"exact": "Exact", "normalized": "Normalized", "fuzzy": "Fuzzy", "semantic": "Same meaning", "ai": "AI matched",
                     "unmatched": "Missing in target", "new": "New in target"}.get(m.method, m.method)
            cls = "ct-Removed" if m.method == "unmatched" else "ct-Added" if m.method == "new" else \
                  "ct-Renamed" if m.ref_column != m.tgt_column else "ct-Modified"
            P.append(f"<tr><td>{_e(m.table_ref)}</td><td class='el'>{_e(m.ref_column or '—')}</td><td>{_e(m.meaning)}</td>"
                     f"<td class='el'>{_e(m.tgt_column or '—')}</td><td><span class='pill {cls}'>{_e(match)}</span></td>"
                     f"<td data-s='{m.confidence:.3f}'>{m.confidence:.0%}</td><td>{'🔑' if is_key else ''}</td>"
                     f"<td class='loc'>{_e(m.note)}</td></tr>")
        P.append("</tbody></table></div>")

    # ---- differences
    P.append("<h2>Differences</h2>")
    if not result.items:
        P.append("<div class='summary'><p>✅ No differences found.</p></div>")
    else:
        cats = sorted({i.category for i in result.items})
        P.append("<div class='toolbar'><input id='q' placeholder='Search differences…'>")
        for k, vals in (("impact", ["High", "Medium", "Low", "Info"]), ("change", ["Added", "Removed", "Modified", "Renamed"]),
                        ("category", cats)):
            for v in vals:
                P.append(f"<span class='chip' data-k='{k}' data-v='{_e(v)}'>{_e(v)}</span>")
        P.append(f"<span class='meta'>showing <b id='shown'>{len(result.items)}</b> / {len(result.items)}</span></div>")
        P.append("<div class='tbl-wrap'><table id='diffs' class='sortable'><thead><tr><th>#</th><th>Impact</th>"
                 "<th>Category</th><th>Change</th><th>Location</th><th>Element</th><th>Reference value</th>"
                 "<th>Target value</th><th>Description</th></tr></thead><tbody>")
        order = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}
        for it in result.items:
            if it.change_type == "Modified" and it.ref_value and it.tgt_value and len(it.ref_value) + len(it.tgt_value) < 6000:
                rv, tv = intraline(it.ref_value, it.tgt_value)
            else:
                rv, tv = _e(it.ref_value), _e(it.tgt_value)
            details = (f"<details><summary>show code / diff</summary><pre class='hunk'>{_hunk_html(it.details)}</pre></details>"
                       if it.details else "")
            ai = "<span class='ai-dot' title='Described by AI agent'>✦AI</span>" if it.ai_described else ""
            P.append(f"<tr data-impact='{_e(it.impact)}' data-change='{_e(it.change_type)}' data-category='{_e(it.category)}'>"
                     f"<td data-s='{it.id}'>{it.id}</td>"
                     f"<td data-s='{order.get(it.impact, 9)}'><span class='pill im-{_e(it.impact)}'>{_e(it.impact)}</span></td>"
                     f"<td>{_e(it.category)}</td><td><span class='pill ct-{_e(it.change_type)}'>{_e(it.change_type)}</span></td>"
                     f"<td class='loc'>{_e(it.location)}</td><td class='el'>{_e(it.element)}</td>"
                     f"<td class='val'>{rv}</td><td class='val'>{tv}</td><td class='desc'>{_e(it.description)}{ai}{details}</td></tr>")
        P.append("</tbody></table></div>")

    # ---- side by side
    if result.side_by_side:
        P.append(f"<h2>Line-by-line view</h2><details><summary>Show side-by-side changes "
                 f"({sum(1 for r in result.side_by_side if r.tag not in ('equal', 'skip'))} changed lines)</summary>"
                 "<div class='tbl-wrap' style='margin-top:10px'><table class='sbs'><tbody>")
        for r in result.side_by_side:
            if r.tag == "skip":
                P.append(f"<tr class='skip'><td colspan='4'>⋯ {_e(r.ref_text)}</td></tr>")
                continue
            if r.tag == "replace":
                a, b = intraline(r.ref_text, r.tgt_text)
            else:
                a, b = _e(r.ref_text), _e(r.tgt_text)
            P.append(f"<tr class='{r.tag}'><td class='no'>{r.ref_no or ''}</td><td class='a t'>{a}</td>"
                     f"<td class='no'>{r.tgt_no or ''}</td><td class='b t'>{b}</td></tr>")
        P.append("</tbody></table></div></details>")

    # ---- agent log
    if result.agent_log:
        P.append("<h2>Agent activity log</h2><details><summary>Show log</summary><div class='log'>"
                 + _e("\n".join(result.agent_log)) + "</div></details>")

    P.append(f"<footer>Generated by <b>AI Compare Studio</b> · reference = baseline, target = new version</footer>"
             f"</div><script>{JS}</script></body></html>")
    return "\n".join(P)


def save_html(result: CompareResult, path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_html(result))
    return path
