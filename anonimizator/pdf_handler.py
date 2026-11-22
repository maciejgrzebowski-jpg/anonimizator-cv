"""Anonimizacja plików PDF (prawdziwe usunięcie tekstu, nie tylko zamalowanie)."""
from __future__ import annotations

try:
    import pymupdf as fitz
except ImportError:  # starsze wersje
    import fitz

import re

from .detector import Finding, token_pattern

PUNCT = ".,;:()[]{}|•·\"'„”“’«»!?"


OCR_DPI = 200
_OCR_CACHE: dict = {}


def _needs_ocr(page) -> bool:
    """Strona-skan: prawie brak tekstu, a większość strony zajmuje obraz."""
    if len(page.get_text("text").strip()) >= 200:
        return False
    area = page.rect.get_area()
    covered = 0.0
    for info in page.get_image_info():
        covered += (fitz.Rect(info["bbox"]) & page.rect).get_area()
    return covered > 0.5 * area


def scanned_pages(path: str) -> list[int]:
    with fitz.open(path) as doc:
        return [p.number for p in doc if _needs_ocr(p)]


def _ocr_page(path: str, page):
    """Słowa z OCR w punktach PDF: (x0, y0, x1, y1, tekst, linia)."""
    import os
    from PIL import Image
    from . import ocr
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size, page.number)
    if key not in _OCR_CACHE:
        pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        z = OCR_DPI / 72
        _OCR_CACHE[key] = [(x0 / z, y0 / z, x1 / z, y1 / z, t, k)
                           for x0, y0, x1, y1, t, k in ocr.ocr_words(img)]
    return _OCR_CACHE[key]


def suggest_areas(path: str) -> list[tuple]:
    """Propozycja zdjęcia do zamazania na zeskanowanej 1. stronie."""
    from PIL import Image
    from .image_handler import detect_photos
    with fitz.open(path) as doc:
        page = doc[0]
        if not _needs_ocr(page):
            return []  # zwykły PDF - zdjęcia usuwane są automatycznie
        pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        z = OCR_DPI / 72
        words = [(x0 * z, y0 * z, x1 * z, y1 * z, t, k) for x0, y0, x1, y1, t, k in _ocr_page(path, page)]
    return [(0, *b) for b in detect_photos(img, words)]


def title_lines(path: str) -> list[tuple]:
    """Największe napisy z 1. strony: (wysokość, y, tekst)."""
    from . import ocr
    with fitz.open(path) as doc:
        page = doc[0]
        if _needs_ocr(page):
            return ocr.title_lines(_ocr_page(path, page))
        out = []
        for b in page.get_text("dict").get("blocks", []):
            for l in b.get("lines", []):
                spans = [s for s in l.get("spans", []) if s.get("text", "").strip()]
                if spans:
                    size = max(s.get("size", 0) for s in spans)
                    out.append((size, l["bbox"][1], "".join(s["text"] for s in spans).strip()))
    return sorted(out, key=lambda t: -t[0])


def extract_lines(path: str) -> list[str]:
    from . import ocr
    lines: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            if _needs_ocr(page):
                lines.extend(ocr.words_to_lines(_ocr_page(path, page)))
            else:
                lines.extend(page.get_text("text").splitlines())
    return lines


def _norm(w: str) -> str:
    return w.strip(PUNCT)


def _overlaps(r, rects) -> bool:
    for o in rects:
        i = r & o
        if not i.is_empty and i.get_area() > 0.5 * min(r.get_area(), o.get_area()):
            return True
    return False


def _span_style(page, rect):
    """Kolor i rozmiar oryginalnego tekstu w danym miejscu."""
    try:
        d = page.get_text("dict", clip=rect)
        for b in d.get("blocks", []):
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s.get("text", "").strip():
                        c = s.get("color", 0)
                        rgb = ((c >> 16) & 255, (c >> 8) & 255, c & 255)
                        return tuple(x / 255 for x in rgb), float(s.get("size", 10))
    except Exception:
        pass
    return (0, 0, 0), 10.0


def _word_hits(words, f: Finding, used: set) -> list[list]:
    """Wyszukiwanie całych słów (imiona, nazwiska) - zwraca grupy prostokątów."""
    toks = [re.compile(token_pattern(t, f.inflect), re.IGNORECASE) for t in f.text.split()]
    n = len(toks)
    hits = []
    i = 0
    while i <= len(words) - n:
        idx = list(range(i, i + n))
        if not any(k in used for k in idx) and all(toks[j].fullmatch(_norm(words[k][4])) for j, k in enumerate(idx)):
            used.update(idx)
            # grupuj po liniach (block, line)
            groups: dict = {}
            for k in idx:
                w = words[k]
                groups.setdefault((w[5], w[6]), fitz.Rect(w[:4]))
                groups[(w[5], w[6])] |= fitz.Rect(w[:4])
            hits.append(list(groups.values()))
            i += n
        else:
            i += 1
    return hits


def _add_label(page, rect, label: str, blackout: bool):
    if blackout:
        page.add_redact_annot(rect, fill=(0, 0, 0))
        return
    if not label:
        page.add_redact_annot(rect, fill=(1, 1, 1))
        return
    color, size = _span_style(page, rect)
    fs = min(size, rect.height / 1.3)  # musi zmieścić się w wysokości pola
    text = label
    while fs > 5 and fitz.get_text_length(text, "helv", fs) > rect.width:
        fs -= 0.25
    if fitz.get_text_length(text, "helv", fs) > rect.width:
        text, fs = "***", min(size, rect.height / 1.3)
        while fs > 3 and fitz.get_text_length(text, "helv", fs) > rect.width:
            fs -= 0.25
    kw = dict(text=text, fontname="helv", fontsize=fs, text_color=color)
    try:
        # bez wypełnienia - zostaje oryginalne tło (np. kolorowy pasek boczny)
        page.add_redact_annot(rect, fill=False, **kw)
    except Exception:
        page.add_redact_annot(rect, fill=(1, 1, 1), **kw)


def _redact_images_mode():
    # PIXELS = wymaż tylko piksele obrazu pod zaznaczeniem (ważne dla skanów z warstwą tekstu)
    return getattr(fitz, "PDF_REDACT_IMAGE_PIXELS", fitz.PDF_REDACT_IMAGE_NONE)


def _apply(page, images):
    kwargs = dict(images=images)
    if hasattr(fitz, "PDF_REDACT_LINE_ART_NONE"):
        kwargs["graphics"] = fitz.PDF_REDACT_LINE_ART_NONE
    try:
        page.apply_redactions(**kwargs)
    except TypeError:
        page.apply_redactions(images=images)


def anonymize(path: str, out_path: str, findings: list[Finding], blackout: bool = False,
              remove_photos: bool = True, manual=None) -> dict:
    active = [f for f in findings if f.enabled]
    stats = {"zamiany": 0, "zdjecia": 0, "linki": 0}
    doc = fitz.open(path)

    for page in doc:
        # 1) zdjęcie kandydata (obrazy na 1. stronie, nie tła i nie małe ikonki)
        if remove_photos and page.number == 0:
            pr = page.rect
            n = 0
            for info in page.get_image_info():
                r = fitz.Rect(info["bbox"]) & pr
                if r.width >= 40 and r.height >= 40 and r.width < pr.width * 0.6 and r.height < pr.height * 0.5:
                    try:
                        page.add_redact_annot(r, fill=False)  # zostaje tło strony
                    except Exception:
                        page.add_redact_annot(r, fill=(1, 1, 1))
                    n += 1
            if n:
                _apply(page, fitz.PDF_REDACT_IMAGE_REMOVE)
                stats["zdjecia"] += n

        # 2a) ręcznie zaznaczone obszary (np. zdjęcie na skanie)
        n_manual = 0
        for pnum, fx0, fy0, fx1, fy1 in manual or []:
            if pnum == page.number:
                pr = page.rect
                r = fitz.Rect(pr.x0 + fx0 * pr.width, pr.y0 + fy0 * pr.height,
                              pr.x0 + fx1 * pr.width, pr.y0 + fy1 * pr.height)
                page.add_redact_annot(r, fill=(0, 0, 0) if blackout else (1, 1, 1))
                n_manual += 1
        if n_manual:
            _apply(page, _redact_images_mode())
            stats["zdjecia"] += n_manual

        # 2b) skan: tekst z OCR, zamalowanie pikseli
        if _needs_ocr(page):
            from . import ocr
            hits = ocr.match_boxes(_ocr_page(path, page), active)
            for x0, y0, x1, y1, label, _ in hits:
                r = fitz.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
                if blackout:
                    page.add_redact_annot(r, fill=(0, 0, 0))
                else:
                    fs = min(r.height / 1.3, 11)
                    while fs > 4 and fitz.get_text_length(label, "helv", fs) > r.width:
                        fs -= 0.25
                    page.add_redact_annot(r, text=label if fs > 4 else "", fontname="helv",
                                          fontsize=max(fs, 4), fill=(1, 1, 1), text_color=(0, 0, 0))
            if hits:
                _apply(page, _redact_images_mode())
                stats["zamiany"] += len(hits)
            continue

        # 2c) zwykły PDF z tekstem
        words = page.get_text("words")
        used: set = set()
        done: list = []
        for f in active:  # posortowane od najdłuższych
            label = f.replacement
            if f.whole_word:
                for group in _word_hits(words, f, used):
                    for k, r in enumerate(group):
                        if _overlaps(r, done):
                            continue
                        _add_label(page, r, label if k == 0 else "", blackout)
                        done.append(r)
                        stats["zamiany"] += 1
            else:
                for r in page.search_for(f.text):
                    if _overlaps(r, done):
                        continue
                    _add_label(page, r, label, blackout)
                    done.append(r)
                    stats["zamiany"] += 1

        # 3) klikalne linki (mailto:, LinkedIn itp.)
        for link in page.get_links():
            uri = (link.get("uri") or "").casefold()
            if not uri:
                continue
            if uri.startswith(("mailto:", "tel:")) or any(
                    f.key.replace(" ", "") in uri for f in active if len(f.key) >= 4):
                page.delete_link(link)
                stats["linki"] += 1

        if done:
            _apply(page, _redact_images_mode())

    # 4) metadane i spis treści
    # czyścimy metadane; zostaje tylko informacja o bibliotece (prośba licencji AGPL PyMuPDF)
    meta = {k: "" for k in ("author", "title", "subject", "keywords", "creator",
                            "creationDate", "modDate")}
    meta["producer"] = f"PyMuPDF {getattr(fitz, 'VersionBind', '')} (AGPL-3.0) / Anonimizator CV"
    doc.set_metadata(meta)
    if any((doc.metadata or {}).get(k) for k in ("author", "title", "subject", "keywords", "creator")):
        doc.xref_set_key(-1, "Info", "null")  # awaryjnie: usuń cały blok metadanych
    try:
        doc.del_xml_metadata()
    except Exception:
        pass
    toc = doc.get_toc(simple=True)
    if toc:
        for entry in toc:
            for f in active:
                if f.key in entry[1].casefold():
                    entry[1] = f.replacement
        doc.set_toc(toc)

    doc.save(out_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return stats
