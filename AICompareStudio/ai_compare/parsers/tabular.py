"""Excel / CSV parsing."""
from __future__ import annotations

import csv
import datetime as _dt
import os

from ..models import ParsedDocument, Table


def cell_to_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return repr(v)
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat(sep=" ") if isinstance(v, _dt.datetime) else v.isoformat()
    return str(v).strip()


def detect_header_row(rows: list[list[str]], scan: int = 15) -> int:
    """Return index of the most likely header row (first dense, mostly-text row)."""
    best, best_score = 0, -1.0
    for i, row in enumerate(rows[:scan]):
        cells = [c for c in row if c != ""]
        if not cells:
            continue
        texty = sum(1 for c in cells if not _is_number(c))
        uniq = len(set(cells)) / len(cells)
        score = len(cells) * (texty / len(cells)) * uniq
        if score > best_score + 0.5:   # prefer earlier rows on ties
            best, best_score = i, score
    return best


def _is_number(s: str) -> bool:
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        return False


def rows_to_table(name: str, rows: list[list[str]], location: str) -> Table | None:
    rows = [r for r in rows if any(c != "" for c in r)]
    if not rows:
        return None
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    # Drop fully empty columns
    keep = [j for j in range(width) if any(r[j] != "" for r in rows)]
    rows = [[r[j] for j in keep] for r in rows]
    h = detect_header_row(rows)
    headers_raw = rows[h]
    headers, seen = [], {}
    for j, hname in enumerate(headers_raw):
        hname = " ".join(hname.split()) or f"Column {j + 1}"
        if hname in seen:
            seen[hname] += 1
            hname = f"{hname} ({seen[hname]})"
        else:
            seen[hname] = 1
        headers.append(hname)
    return Table(name=name, headers=headers, rows=rows[h + 1:], location=location)


def parse_excel(path: str) -> ParsedDocument:
    doc = ParsedDocument(path=path, file_type="excel")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xls":
        import xlrd
        book = xlrd.open_workbook(path)
        for sh in book.sheets():
            rows = [[cell_to_str(sh.cell_value(r, c)) for c in range(sh.ncols)] for r in range(sh.nrows)]
            t = rows_to_table(sh.name, rows, f"Sheet '{sh.name}'")
            if t:
                doc.tables.append(t)
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        for ws in wb.worksheets:
            rows = [[cell_to_str(v) for v in r] for r in ws.iter_rows(values_only=True)]
            t = rows_to_table(ws.title, rows, f"Sheet '{ws.title}'")
            if t:
                doc.tables.append(t)
        wb.close()
    if not doc.tables:
        doc.warnings.append("Workbook contains no data.")
    return doc


def parse_csv(path: str) -> ParsedDocument:
    doc = ParsedDocument(path=path, file_type="csv")
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = [[c.strip() for c in r] for r in csv.reader(fh, dialect)]
    t = rows_to_table(os.path.splitext(os.path.basename(path))[0], rows, "CSV")
    if t:
        doc.tables.append(t)
    return doc
