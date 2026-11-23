"""Command line interface: python -m ai_compare cli REF TARGET -o report.html"""
from __future__ import annotations

import argparse
import os
import sys

from .ai_agent import DEFAULT_MODEL, AgentConfig
from .comparator import compare_files
from .report import save_html


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ai_compare cli", description="AI-assisted file comparison (headless).")
    p.add_argument("reference", help="Reference (baseline) file")
    p.add_argument("target", help="Target (new) file")
    p.add_argument("-o", "--output", help="HTML report path (default: <target>_diff_report.html)")
    p.add_argument("--no-ai", action="store_true", help="Use only the rule-based engine")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--max-ai-items", type=int, default=400)
    a = p.parse_args(argv)
    cfg = AgentConfig(enabled=not a.no_ai, model=a.model, effort=a.effort, max_ai_items=a.max_ai_items,
                      api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    try:
        res = compare_files(a.reference, a.target, cfg)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    out = a.output or os.path.splitext(a.target)[0] + "_diff_report.html"
    save_html(res, out)
    print(f"Report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
