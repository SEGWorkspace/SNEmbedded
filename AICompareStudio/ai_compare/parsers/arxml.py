"""AUTOSAR ARXML parser.

Every element that owns a SHORT-NAME becomes an addressable ArxmlElement whose
path is built from the SHORT-NAME hierarchy (e.g. /Signals/ISignals/EngineSpeed).
Its properties are all leaf values beneath it that do not belong to a nested
named element, keyed by their relative tag path, plus XML attributes such as DEST.
"""
from __future__ import annotations

from collections import Counter

from lxml import etree

from ..models import ArxmlElement, ArxmlModel, ParsedDocument, TextBlock


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _short_name(el) -> str | None:
    for ch in el:
        if _local(ch.tag) == "SHORT-NAME":
            return (ch.text or "").strip()
    return None


def parse_arxml(path: str) -> ParsedDocument:
    doc = ParsedDocument(path=path, file_type="arxml")
    parser = etree.XMLParser(remove_blank_text=False, recover=True, huge_tree=True)
    tree = etree.parse(path, parser)
    root = tree.getroot()
    model = ArxmlModel()
    ns = root.nsmap.get(None, "")
    if ns:
        model.autosar_version = ns.rsplit("/", 1)[-1]
    schema = root.get("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", "")
    if schema:
        model.autosar_version = schema.split()[-1]

    def collect_props(el, prefix: str, props: dict[str, str]):
        counts = Counter(_local(c.tag) for c in el if isinstance(c.tag, str))
        seen: Counter = Counter()
        for ch in el:
            if not isinstance(ch.tag, str):
                continue
            tag = _local(ch.tag)
            if tag == "SHORT-NAME":
                continue
            seen[tag] += 1
            idx = f"[{seen[tag]}]" if counts[tag] > 1 else ""
            if _short_name(ch) is not None:
                continue            # nested named element – compared as its own element
            key = f"{prefix}{tag}{idx}"
            for an, av in ch.attrib.items():
                props[f"{key}/@{_local(an)}"] = av
            if len(ch):
                collect_props(ch, key + "/", props)
            else:
                props[key] = " ".join((ch.text or "").split())

    def walk(el, path: str):
        sn = _short_name(el)
        cur = path
        if sn is not None:
            cur = f"{path}/{sn}"
            props: dict[str, str] = {}
            for an, av in el.attrib.items():
                props[f"@{_local(an)}"] = av
            collect_props(el, "", props)
            model.elements.append(ArxmlElement(path=cur, tag=_local(el.tag), properties=props,
                                               line=el.sourceline or 0))
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch, cur)

    walk(root, "")
    doc.arxml = model
    with open(path, encoding="utf-8", errors="replace") as fh:
        doc.raw_lines = fh.read().splitlines()
    for i, line in enumerate(doc.raw_lines, start=1):
        if line.strip():
            doc.text_blocks.append(TextBlock(location=f"Line {i}", text=line))
    if not model.elements:
        doc.warnings.append("No SHORT-NAME elements found – is this a valid ARXML file?")
    return doc
