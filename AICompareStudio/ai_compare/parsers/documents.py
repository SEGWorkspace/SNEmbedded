"""Word (.docx), PDF and plain-text / notes parsing."""
from __future__ import annotations

from ..models import ParsedDocument, TextBlock
from .tabular import rows_to_table


def parse_docx(path: str) -> ParsedDocument:
    import docx
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph

    doc = ParsedDocument(path=path, file_type="word")
    d = docx.Document(path)
    heading = "Document start"
    para_no = 0
    table_no = 0
    # Walk the body in order so tables keep their position relative to headings.
    for child in d.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, d)
            text = p.text.strip()
            if not text:
                continue
            para_no += 1
            style = p.style.name if p.style is not None else ""
            if style.lower().startswith("heading") or style.lower() == "title":
                heading = text
            doc.text_blocks.append(TextBlock(location=f"§ {heading} · para {para_no}", text=text, style=style))
        elif tag == "tbl":
            table_no += 1
            t = DocxTable(child, d)
            rows = []
            for r in t.rows:
                row, last = [], None
                for c in r.cells:            # merged cells repeat – collapse them
                    if c._tc is last:
                        continue
                    last = c._tc
                    row.append(" ".join(c.text.split()))
                rows.append(row)
            tbl = rows_to_table(f"Table {table_no}", rows, f"Table {table_no} (under '{heading}')")
            if tbl:
                doc.tables.append(tbl)
    doc.raw_lines = [b.text for b in doc.text_blocks]
    return doc


def parse_pdf(path: str) -> ParsedDocument:
    import pdfplumber

    doc = ParsedDocument(path=path, file_type="pdf")
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            text_page = page
            try:
                for tno, ft in enumerate(page.find_tables() or [], start=1):
                    raw = ft.extract()
                    rows = [[" ".join((c or "").split()) for c in r] for r in raw]
                    if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        t = rows_to_table(f"Page {pno} table {tno}", rows, f"Page {pno}, table {tno}")
                        if t:
                            doc.tables.append(t)
                            text_page = text_page.outside_bbox(ft.bbox)   # avoid double reporting
            except Exception as exc:  # table extraction is best effort
                doc.warnings.append(f"Page {pno}: table extraction failed ({exc})")
            text = text_page.extract_text() or ""
            for lno, line in enumerate(text.splitlines(), start=1):
                line = line.strip()
                if line:
                    doc.text_blocks.append(TextBlock(location=f"Page {pno}, line {lno}", text=line))
    if not doc.text_blocks and not doc.tables:
        doc.warnings.append("No extractable text – the PDF may be scanned (image only).")
    doc.raw_lines = [b.text for b in doc.text_blocks]
    return doc


def read_text_file(path: str) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                data = fh.read()
            if enc == "utf-16" and "\x00" in data:
                continue
            return data
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def parse_text(path: str) -> ParsedDocument:
    doc = ParsedDocument(path=path, file_type="text")
    lines = read_text_file(path).splitlines()
    doc.raw_lines = lines
    for i, line in enumerate(lines, start=1):
        if line.strip():
            doc.text_blocks.append(TextBlock(location=f"Line {i}", text=line.rstrip()))
    return doc
