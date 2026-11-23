"""File-type detection and dispatch to the right parser."""
from __future__ import annotations

import os

from ..models import ParsedDocument

EXCEL_EXT = {".xlsx", ".xlsm", ".xls"}
CSV_EXT = {".csv", ".tsv"}
WORD_EXT = {".docx", ".docm"}
PDF_EXT = {".pdf"}
CODE_EXT = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".inl"}
ARXML_EXT = {".arxml"}
TEXT_EXT = {".txt", ".md", ".log", ".note", ".notes", ".ini", ".cfg", ".json", ".xml", ".yaml", ".yml", ".rst"}

SUPPORTED_EXT = sorted(EXCEL_EXT | CSV_EXT | WORD_EXT | PDF_EXT | CODE_EXT | ARXML_EXT | TEXT_EXT)

FILE_DIALOG_FILTER = (
    "All supported (" + " ".join(f"*{e}" for e in SUPPORTED_EXT) + ");;"
    "AUTOSAR (*.arxml);;"
    "C / C++ (*.c *.h *.cpp *.cc *.cxx *.hpp *.hh *.hxx);;"
    "Excel / CSV (*.xlsx *.xlsm *.xls *.csv *.tsv);;"
    "Word (*.docx);;PDF (*.pdf);;"
    "Notes / text (*.txt *.md *.log *.note *.ini *.cfg *.json *.xml *.yaml *.yml);;"
    "All files (*)"
)


def parse_file(path: str) -> ParsedDocument:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in EXCEL_EXT:
        from .tabular import parse_excel
        return parse_excel(path)
    if ext in CSV_EXT:
        from .tabular import parse_csv
        return parse_csv(path)
    if ext in WORD_EXT:
        from .documents import parse_docx
        return parse_docx(path)
    if ext == ".doc":
        raise ValueError("Legacy .doc is not supported – please save the file as .docx.")
    if ext in PDF_EXT:
        from .documents import parse_pdf
        return parse_pdf(path)
    if ext in CODE_EXT:
        from .code import parse_code
        return parse_code(path)
    if ext in ARXML_EXT:
        from .arxml import parse_arxml
        return parse_arxml(path)
    from .documents import parse_text
    return parse_text(path)
