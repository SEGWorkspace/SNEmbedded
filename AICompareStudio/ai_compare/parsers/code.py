"""Lightweight C / C++ structural parser (no compiler needed).

Extracts includes, macros, functions, prototypes, structs/unions/enums/classes,
typedefs and global variables so that two versions can be compared symbol by
symbol instead of only line by line.
"""
from __future__ import annotations

import os
import re

from ..models import CodeModel, CodeSymbol, ParsedDocument
from .documents import read_text_file

_IDENT = r"[A-Za-z_]\w*"
_KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "else", "do", "case"}


def strip_comments_and_strings(src: str) -> str:
    """Replace comments, string and char literals by spaces, keeping offsets/newlines."""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            for k in range(i + 1, j - 1):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def _line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def _norm(s: str) -> str:
    return " ".join(s.split())


def _match_brace(s: str, open_pos: int) -> int:
    depth = 0
    for k in range(open_pos, len(s)):
        if s[k] == "{":
            depth += 1
        elif s[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return len(s) - 1


def _func_name(header: str) -> str | None:
    # first '(' that is not part of a macro-ish attribute: take identifier right before it
    for m in re.finditer(r"((?:" + _IDENT + r"\s*::\s*)*~?" + _IDENT + r"|operator\s*[^\s(]+)\s*\(", header):
        name = re.sub(r"\s+", "", m.group(1))
        if name.split("::")[-1] in _KEYWORDS or name in ("__attribute__", "__declspec", "alignas"):
            continue
        return name
    return None


def parse_code(path: str) -> ParsedDocument:
    src = read_text_file(path).replace("\r\n", "\n")
    ext = os.path.splitext(path)[1].lower()
    lang = "C" if ext in (".c", ".h") else "C++"
    doc = ParsedDocument(path=path, file_type="code", raw_lines=src.split("\n"))
    model = CodeModel(language=lang)
    clean = strip_comments_and_strings(src)

    # ---- preprocessor ----------------------------------------------------- #
    pp_mask = list(clean)
    for m in re.finditer(r"^[ \t]*#(?:[^\n\\]|\\.)*(?:\\\n(?:[^\n\\]|\\.)*)*", clean, re.M):
        raw = src[m.start():m.end()]
        line = _line_of(src, m.start())
        directive = _norm(raw.replace("\\\n", " "))
        inc = re.match(r"#\s*include\s*([<\"].*?[>\"])", directive)
        dfn = re.match(r"#\s*define\s+(" + _IDENT + r")(\([^)]*\))?\s*(.*)", directive)
        if inc:
            model.symbols.append(CodeSymbol("include", inc.group(1), directive, directive, line))
        elif dfn:
            name, params, value = dfn.group(1), dfn.group(2) or "", dfn.group(3)
            cvalue = _norm(strip_comments_and_strings(value)) if value else ""
            model.symbols.append(CodeSymbol("macro", name, f"#define {name}{params}", cvalue, line))
        for k in range(m.start(), m.end()):
            if pp_mask[k] != "\n":
                pp_mask[k] = " "
    clean = "".join(pp_mask)

    # ---- top level declarations ------------------------------------------ #
    i, n, stmt_start = 0, len(clean), 0
    transparent_depth = 0      # namespace / extern "C" blocks we descend into
    while i < n:
        c = clean[i]
        if c == "{":
            header_raw = src[stmt_start:i]
            header = _norm(clean[stmt_start:i])
            if re.match(r"^(namespace\b.*|extern\s*)$", header) or re.match(r'^extern\s+"C"', _norm(header_raw)):
                ns = re.match(r"namespace\s+(" + _IDENT + ")", header)
                if ns:
                    model.symbols.append(CodeSymbol("namespace", ns.group(1), header, "", _line_of(src, i)))
                transparent_depth += 1
                i += 1
                stmt_start = i
                continue
            end = _match_brace(clean, i)
            line = _line_of(src, stmt_start + (len(header_raw) - len(header_raw.lstrip())))
            if "=" in header and "(" not in header.split("=")[0][-1:]:
                # initialised global: int table[] = { ... };
                semi = clean.find(";", end)
                semi = n - 1 if semi == -1 else semi
                name = re.findall(_IDENT, header.split("=")[0])
                nm = name[-1] if name else "anonymous"
                model.symbols.append(CodeSymbol("global", nm, _norm(header.split("=")[0]),
                                                src[stmt_start:semi + 1].strip(), line))
                i = semi + 1
                stmt_start = i
                continue
            agg = re.match(r"^(typedef\s+)?(?:\w+\s+)*?(struct|union|enum|class)\b\s*(" + _IDENT + r")?", header)
            if agg and "(" not in header:
                semi = clean.find(";", end)
                tail = _norm(clean[end + 1:semi]) if semi != -1 else ""
                kind = agg.group(2)
                name = agg.group(3) or ""
                if agg.group(1) and tail:
                    name = re.findall(_IDENT, tail)[-1] if re.findall(_IDENT, tail) else name
                    kind = f"typedef {kind}"
                model.symbols.append(CodeSymbol(kind, name or f"anonymous@{line}", header,
                                                src[stmt_start:(semi + 1 if semi != -1 else end + 1)].strip(), line))
                i = (semi + 1) if semi != -1 else end + 1
                stmt_start = i
                continue
            name = _func_name(header)
            kind = "function" if name else "block"
            model.symbols.append(CodeSymbol(kind, name or f"block@{line}", header,
                                            src[stmt_start:end + 1].strip(), line))
            i = end + 1
            stmt_start = i
            continue
        if c == "}" and transparent_depth:
            transparent_depth -= 1
            i += 1
            stmt_start = i
            continue
        if c == ";":
            header = _norm(clean[stmt_start:i])
            line = _line_of(src, stmt_start + (len(src[stmt_start:i]) - len(src[stmt_start:i].lstrip())))
            raw = src[stmt_start:i + 1].strip()
            if header and not header.startswith(("using ", "template")):
                if header.startswith("typedef"):
                    ids = re.findall(_IDENT, re.sub(r"\(\s*\*\s*(" + _IDENT + r")\s*\)", r" \1 ", header))
                    fp = re.search(r"\(\s*\*\s*(" + _IDENT + r")\s*\)", header)
                    nm = fp.group(1) if fp else (ids[-1] if ids else "typedef")
                    model.symbols.append(CodeSymbol("typedef", nm, header, raw, line))
                elif "(" in header and "=" not in header.split("(")[0]:
                    nm = _func_name(header)
                    if nm:
                        model.symbols.append(CodeSymbol("prototype", nm, header, raw, line))
                else:
                    decl = header.split("=")[0]
                    decl = re.sub(r"\[.*?\]", "", decl)
                    ids = re.findall(_IDENT, decl)
                    if ids:
                        model.symbols.append(CodeSymbol("global", ids[-1], _norm(decl), raw, line))
            i += 1
            stmt_start = i
            continue
        i += 1

    doc.code = model
    for idx, line in enumerate(doc.raw_lines, start=1):
        from ..models import TextBlock
        if line.strip():
            doc.text_blocks.append(TextBlock(location=f"Line {idx}", text=line))
    return doc
