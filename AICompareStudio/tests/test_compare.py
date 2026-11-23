"""Tests: python -m pytest tests -q   (run samples/make_samples.py first)"""
import json
import os
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SAMPLES = os.path.join(ROOT, "samples")

from ai_compare.ai_agent import AgentConfig, CompareAgent  # noqa: E402
from ai_compare.comparator import compare_files  # noqa: E402
from ai_compare.report import build_html  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def samples():
    subprocess.run([sys.executable, os.path.join(SAMPLES, "make_samples.py")], check=True, capture_output=True)


def run(name, cfg=None):
    return compare_files(os.path.join(SAMPLES, "ref_" + name), os.path.join(SAMPLES, "tgt_" + name),
                         cfg or AgentConfig(enabled=False), log=lambda m: None)


def find(res, **kw):
    return [i for i in res.items if all(v in getattr(i, k) for k, v in kw.items())]


def test_excel_columns_mapped_by_meaning():
    r = run("signals.xlsx")
    m = {x.ref_column: x.tgt_column for x in r.mappings if x.ref_column}
    assert m["Signal Name"] == "Signal" and m["Message ID"] == "CAN ID"
    assert m["Length"] == "Bit Length" and m["Factor"] == "Scaling"
    assert r.key_columns["Signals"] == ["Signal Name"]
    assert find(r, element="EngineSpeed → Factor")[0].tgt_value == "0.125"
    assert find(r, change_type="Removed", element="BrakePressed")
    assert find(r, change_type="Added", element="GearPosition")
    assert find(r, category="Structure", element="Nodes")


def test_code_header():
    r = run("can_if.h")
    assert find(r, element="macro CANIF_MAX_PDUS")[0].impact == "High"
    assert find(r, element="CanIf_Transmit (signature)")
    assert find(r, change_type="Added", element="CANIF_FD_SUPPORT")
    assert not find(r, element="CANIF_TX_TIMEOUT_MS")       # only a comment was added


def test_code_source():
    r = run("can_if.c")
    assert find(r, change_type="Removed", element="CanIf_ClearBuffers")
    assert find(r, change_type="Added", element="CanIf_GetTxErrorCount")
    assert find(r, element="function CanIf_GetMode")[0].impact == "Info"


def test_cpp():
    r = run("scheduler.cpp")
    assert find(r, element="Scheduler_Run (signature)")
    assert find(r, element="function tickPeriodMs")


def test_arxml():
    r = run("com.arxml")
    assert find(r, change_type="Renamed", element="/Signals/CoolantTemp")
    assert find(r, element="/Signals/VehicleSpeed :: LENGTH")[0].tgt_value == "16"
    assert find(r, element="START-POSITION")[0].impact == "High"
    assert find(r, change_type="Added", element="/Signals/GearPosition")


def test_docx_pdf_notes():
    d = run("spec.docx")
    assert find(d, category="Table", element="LockSpeed → Value")
    assert find(d, category="Text", change_type="Added")
    p = run("report.pdf")
    assert find(p, element="TC_003 Sleep → Result")[0].tgt_value == "PASS"
    assert not find(p, category="Text", element="TC_001")     # table text not double-reported
    n = run("notes.txt")
    assert find(n, change_type="Modified", ref_value="15 km/h")[0].impact == "High"


def test_html_report():
    html = build_html(run("signals.xlsx"))
    assert "Column understanding" in html and "Differences" in html and "#d4af37" in html


# ----------------------------------------------------------------------------- mocked agent
def _tool_use(name, args, i):
    return NS(type="tool_use", name=name, input=args, id=f"tu_{i}")


def _resp(stop, *content):
    return NS(stop_reason=stop, content=list(content))


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        task = kw["messages"][0]["content"]
        n = len(kw["messages"])
        if "PHASE 1" in task:
            if n == 1:
                return _resp("tool_use", NS(type="text", text="Let me look at the tables."),
                             _tool_use("list_tables", {}, 1))
            if n == 3:
                return _resp("tool_use", _tool_use("profile_column",
                                                   {"side": "reference", "table": "Signals", "column": "Factor"}, 2),
                             _tool_use("compare_column_values", {"ref_table": "Signals", "ref_column": "Description",
                                                                 "tgt_table": "Signals", "tgt_column": "Comment"}, 3))
            cols = [("Signal Name", "Signal"), ("Message ID", "CAN ID"), ("Start Bit", "Start Bit"),
                    ("Length", "Bit Length"), ("Factor", "Scaling"), ("Unit", "Unit"), ("Description", "Comment")]
            return _resp("end_turn", NS(type="text", text=json.dumps({"tables": [{
                "ref_table": "Signals", "tgt_table": "Signals", "key_columns": ["Signal Name"],
                "columns": [{"ref_column": a, "meaning": f"meaning of {a}", "tgt_column": b, "confidence": 0.9,
                             "reasoning": "same values"} for a, b in cols]}], "notes": "ok"})))
        if "PHASE 2" in task:
            ids = [d["id"] for d in json.loads(task[task.index("["):])]
            return _resp("end_turn", NS(type="text", text=json.dumps(
                {"items": [{"id": i, "description": f"AI text {i}", "impact": "Medium"} for i in ids]})))
        if "PHASE 3" in task:
            if n == 1:
                return _resp("tool_use", _tool_use("get_diff_statistics", {}, 9))
            assert kw["messages"][-1]["content"][0]["type"] == "tool_result"
            return _resp("end_turn", NS(type="text", text=json.dumps(
                {"executive_summary": "AI summary", "overall_risk": "High", "key_findings": ["f1", "f2"]})))
        raise AssertionError("unexpected task")


def test_agent_pipeline_with_mock(monkeypatch):
    fake = FakeMessages()
    monkeypatch.setattr(CompareAgent, "client", lambda self: NS(beta=NS(messages=fake)))
    monkeypatch.setattr(CompareAgent, "ready", lambda self: (True, ""))
    r = run("signals.xlsx", AgentConfig(enabled=True, workers=1))
    assert r.ai_used and r.executive_summary == "AI summary" and r.overall_risk == "High"
    assert all(i.ai_described and i.description.startswith("AI text") for i in r.items)
    assert {m.ref_column: m.method for m in r.mappings}["Factor"] == "ai"
    first = fake.calls[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default" and first["output_config"]["format"]["type"] == "json_schema"
    assert all(t["strict"] for t in first["tools"])
