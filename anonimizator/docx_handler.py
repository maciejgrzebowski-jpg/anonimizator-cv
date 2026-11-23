"""Anonimizacja plików Word (.docx) z zachowaniem formatowania."""
from __future__ import annotations

import re

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml import etree

from .detector import Finding, build_pattern

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
BLACKOUT = "█████"

# części dokumentu, które mogą zawierać tekst
WML_TYPES = ("document.main", "header", "footer", "footnotes", "endnotes", "comments")


def _text_parts(doc):
    """Zwraca (część, korzeń XML, czy_trzeba_zapisac_blob) dla wszystkich części z tekstem."""
    out = []
    for part in doc.part.package.iter_parts():
        ct = part.content_type or ""
        if "wordprocessingml" not in ct or not any(t in ct for t in WML_TYPES):
            continue
        el = getattr(part, "_element", None)
        if el is not None:
            out.append((part, el, False))
        else:
            out.append((part, etree.fromstring(part.blob), True))
    return out


def _paragraph_segments(p):
    """Lista (element w:t lub None, tekst) w kolejności występowania w akapicie."""
    segs = []
    for el in p.iter(f"{{{W}}}t", f"{{{W}}}tab", f"{{{W}}}br", f"{{{W}}}cr"):
        # pomijamy tekst w zagnieżdżonych akapitach (pola tekstowe) – obsłużymy je osobno
        anc = el.getparent()
        while anc is not None and anc.tag != f"{{{W}}}p":
            anc = anc.getparent()
        if anc is not p:
            continue
        if el.tag == f"{{{W}}}t":
            segs.append((el, el.text or ""))
        else:
            segs.append((None, "\t" if el.tag.endswith("tab") else "\n"))
    return segs


def extract_lines(path: str) -> list[str]:
    doc = Document(path)
    lines: list[str] = []
    parts = _text_parts(doc)
    # nagłówki najpierw (tam często jest imię i nazwisko), potem treść, reszta na końcu
    order = {"header": 0, "document.main": 1}
    parts.sort(key=lambda x: next((v for k, v in order.items() if k in x[0].content_type), 2))
    for _, root, _ in parts:
        for p in root.iter(f"{{{W}}}p"):
            text = "".join(t for _, t in _paragraph_segments(p))
            lines.extend(text.split("\n"))
    return lines


def _apply_to_paragraph(p, patterns) -> int:
    segs = _paragraph_segments(p)
    full = "".join(t for _, t in segs)
    if not full.strip():
        return 0
    # zbierz dopasowania (dłuższe znaleziska mają pierwszeństwo, bez nakładania)
    spans = []
    taken = [False] * len(full)
    for rx, repl in patterns:
        for m in rx.finditer(full):
            s, e = m.span()
            if s == e or any(taken[s:e]):
                continue
            for i in range(s, e):
                taken[i] = True
            spans.append((s, e, repl))
    if not spans:
        return 0
    # mapowanie pozycji -> segment
    bounds = []
    pos = 0
    for el, t in segs:
        bounds.append((pos, pos + len(t), el))
        pos += len(t)
    new_text = {id(el): list(t) for el, t in segs if el is not None}
    els = {id(el): el for el, _ in segs if el is not None}
    for s, e, repl in sorted(spans, reverse=True):
        inserted = False
        for bs, be, el in bounds:
            if el is None or be <= s or bs >= e:
                continue
            chars = new_text[id(el)]
            a, b = max(s, bs) - bs, min(e, be) - bs
            chars[a:b] = list(repl) if not inserted else []
            inserted = True
    for k, chars in new_text.items():
        el = els[k]
        txt = "".join(chars)
        if txt != (el.text or ""):
            el.text = txt
            el.set(XML_SPACE, "preserve")
    return len(spans)


R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _image_rids_in(el, image_rids) -> set:
    """Identyfikatory plików obrazów, do których odwołuje się element."""
    out = set()
    for x in el.iter():
        if not isinstance(x.tag, str):
            continue
        for k, v in x.attrib.items():
            if k.startswith(R_NS) and v in image_rids:
                out.add(v)
    return out


def _is_photo_part(part, rid) -> bool:
    """Czy plik obrazu to zdjęcie osoby (EMF/WMF/SVG i logotypy - nie)."""
    import io
    try:
        from PIL import Image
        from .photo import looks_like_photo
        blob = part.related_parts[rid].blob
        return looks_like_photo(Image.open(io.BytesIO(blob)))
    except Exception:
        return False


def _sensitive_target(target: str, findings) -> bool:
    t = target.casefold()
    if t.startswith(("mailto:", "tel:")):
        return True
    return any(f.key.replace(" ", "") in t.replace(" ", "") for f in findings if len(f.key) >= 4)


def anonymize(path: str, out_path: str, findings: list[Finding], blackout: bool = False,
              remove_photos: bool = True) -> dict:
    doc = Document(path)
    active = [f for f in findings if f.enabled]
    patterns = [(build_pattern(f), BLACKOUT if blackout else f.replacement) for f in active]
    stats = {"zamiany": 0, "zdjecia": 0, "linki": 0}

    for part, root, is_blob in _text_parts(doc):
        for p in root.iter(f"{{{W}}}p"):
            stats["zamiany"] += _apply_to_paragraph(p, patterns)
        # kody pól (np. HYPERLINK "mailto:...")
        for it in root.iter(f"{{{W}}}instrText"):
            txt = it.text or ""
            for rx, repl in patterns:
                txt = rx.sub(repl.replace("\\", "\\\\"), txt)
            if re.search(r"(?i)mailto:|tel:", txt):
                txt = re.sub(r'(?i)HYPERLINK\s+"[^"]*"', 'HYPERLINK "#"', txt)
            it.text = txt
        # hiperłącza wskazujące na e-mail / LinkedIn itp.
        rels = part.rels
        for h in list(root.iter(f"{{{W}}}hyperlink")):
            rid = h.get(f"{{{R}}}id")
            rel = rels.get(rid) if rid else None
            if rel is not None and rel.is_external and _sensitive_target(rel.target_ref, active):
                parent = h.getparent()
                idx = parent.index(h)
                for child in list(h):
                    parent.insert(idx, child)
                    idx += 1
                parent.remove(h)
                rel._target = "#"
                stats["linki"] += 1
        for rel in rels.values():
            if rel.reltype == RT.HYPERLINK and rel.is_external and _sensitive_target(rel.target_ref, active):
                rel._target = "#"
        # zdjęcia: zwykłe obrazy, kształty wypełnione zdjęciem, stare obiekty VML/OLE, tło strony
        if remove_photos:
            image_rids = {rid for rid, rel in part.rels.items() if rel.reltype == RT.IMAGE}
            for tag in (f"{{{W}}}drawing", f"{{{W}}}pict", f"{{{W}}}object", f"{{{W}}}background"):
                for d in list(root.iter(tag)):
                    if d.getparent() is None:
                        continue
                    rids = _image_rids_in(d, image_rids)
                    if not rids or not any(_is_photo_part(part, r) for r in rids):
                        continue  # bez obrazu albo logo / grafika - zostaje
                    d.getparent().remove(d)
                    stats["zdjecia"] += 1
            # usuń same pliki obrazów z paczki, jeśli nic już do nich nie odwołuje
            xml = etree.tostring(root, encoding=str)
            for rid, rel in list(part.rels.items()):
                if rel.reltype == RT.IMAGE and f'"{rid}"' not in xml:
                    try:
                        part.drop_rel(rid)
                    except Exception:
                        pass
        if is_blob:
            part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    # miniaturka 1. strony zapisana przez Worda (zawiera m.in. zdjęcie kandydata)
    if remove_photos:
        pkg = doc.part.package
        for rid, rel in list(pkg.rels.items()):
            if rel.reltype == RT.THUMBNAIL:
                pkg.rels.pop(rid)
                stats["miniatury"] = stats.get("miniatury", 0) + 1

    # metadane (autor, ostatnio modyfikowany przez itd.)
    cp = doc.core_properties
    cp.author = ""
    cp.last_modified_by = ""
    cp.title = ""
    cp.subject = ""
    cp.keywords = ""
    cp.comments = ""
    cp.category = ""

    doc.save(out_path)
    return stats
