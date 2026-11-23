"""Shared data model used by parsers, the diff engine, the AI agent and the report."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# --------------------------------------------------------------------------- #
# Parsed documents
# --------------------------------------------------------------------------- #
@dataclass
class Table:
    """A rectangular table (Excel sheet, CSV, Word table, PDF table)."""
    name: str
    headers: list[str]
    rows: list[list[str]]
    location: str = ""          # e.g. "Sheet 'Signals'" or "Page 3, table 1"

    def column_values(self, header: str) -> list[str]:
        if header not in self.headers:
            return []
        idx = self.headers.index(header)
        return [r[idx] if idx < len(r) else "" for r in self.rows]


@dataclass
class TextBlock:
    """One paragraph / line of prose with a human readable location."""
    location: str
    text: str
    style: str = ""             # e.g. "Heading 1"


@dataclass
class CodeSymbol:
    kind: str                   # function, prototype, macro, struct, enum, union, typedef, global, include, class, namespace
    name: str
    signature: str
    body: str
    line: int

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.name}"


@dataclass
class CodeModel:
    language: str
    symbols: list[CodeSymbol] = field(default_factory=list)

    def by_key(self) -> dict[str, CodeSymbol]:
        out: dict[str, CodeSymbol] = {}
        for s in self.symbols:
            k = s.key
            n = 2
            while k in out:                 # overloaded functions etc.
                k = f"{s.key}#{n}"
                n += 1
            out[k] = s
        return out


@dataclass
class ArxmlElement:
    path: str                   # /Pkg/SubPkg/ElementName
    tag: str                    # AUTOSAR tag, e.g. I-SIGNAL
    properties: dict[str, str]  # relative-path -> value (leaf texts and attributes)
    line: int = 0


@dataclass
class ArxmlModel:
    autosar_version: str = ""
    elements: list[ArxmlElement] = field(default_factory=list)

    def by_path(self) -> dict[str, ArxmlElement]:
        return {e.path: e for e in self.elements}


@dataclass
class ParsedDocument:
    path: str
    file_type: str              # excel, csv, word, pdf, text, code, arxml
    tables: list[Table] = field(default_factory=list)
    text_blocks: list[TextBlock] = field(default_factory=list)
    code: Optional[CodeModel] = None
    arxml: Optional[ArxmlModel] = None
    raw_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        import os
        return os.path.basename(self.path)

    def table(self, name: str) -> Optional[Table]:
        for t in self.tables:
            if t.name == name:
                return t
        return None


# --------------------------------------------------------------------------- #
# Comparison results
# --------------------------------------------------------------------------- #
@dataclass
class ColumnMapping:
    table_ref: str
    table_tgt: str
    ref_column: str
    tgt_column: Optional[str]   # None => column removed in target
    meaning: str = ""
    confidence: float = 1.0
    method: str = "exact"       # exact / normalized / fuzzy / ai / unmatched / new
    note: str = ""


@dataclass
class DiffItem:
    id: int
    category: str               # Table, Text, Code, ARXML, Structure
    change_type: str            # Added, Removed, Modified, Renamed
    location: str
    element: str
    ref_value: str = ""
    tgt_value: str = ""
    description: str = ""
    impact: str = "Low"         # High, Medium, Low, Info
    details: str = ""           # optional extra (e.g. code hunk)
    ai_described: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SideBySideRow:
    tag: str                    # equal, replace, insert, delete, skip
    ref_no: Optional[int]
    ref_text: str
    tgt_no: Optional[int]
    tgt_text: str


@dataclass
class CompareResult:
    reference: ParsedDocument
    target: ParsedDocument
    mappings: list[ColumnMapping] = field(default_factory=list)
    key_columns: dict[str, list[str]] = field(default_factory=dict)  # table -> key columns
    items: list[DiffItem] = field(default_factory=list)
    side_by_side: list[SideBySideRow] = field(default_factory=list)
    executive_summary: str = ""
    overall_risk: str = ""
    key_findings: list[str] = field(default_factory=list)
    agent_log: list[str] = field(default_factory=list)
    ai_used: bool = False
    model: str = ""
    elapsed_s: float = 0.0

    def counts(self) -> dict[str, int]:
        c = {"Added": 0, "Removed": 0, "Modified": 0, "Renamed": 0}
        for it in self.items:
            c[it.change_type] = c.get(it.change_type, 0) + 1
        return c
