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
    """Zdjęcie wykryte na podglądzie 1. strony - dodatkowe zabezpieczenie, także dla zwykłych PDF
    (łapie zdjęcia zapisane nietypowo, np. jako wzór wypełnienia albo przez maskę)."""
    from PIL import Image
    from .image_handler import find_photos
    with fitz.open(path) as doc:
        page = doc[0]
        if _needs_ocr(page):
            dpi = OCR_DPI
            z = dpi / 72
            words = [(x0 * z, y0 * z, x1 * z, y1 * z, t, k) for x0, y0, x1, y1, t, k in _ocr_page(path, page)]
        else:
            dpi = 100
            z = dpi / 72
            words = [(w[0] * z, w[1] * z, w[2] * z, w[3] * z, w[4], (w[5], w[6]))
                     for w in page.get_text("words")]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return [(0, *b) for b in find_photos(img, words)]


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


def _visible_image_rects(page):
    """[(xref, prostokąt widoczny na stronie)] dla obrazów na stronie.

    Word zapisuje przycięte zdjęcia (np. w kółku) jako większy obraz + przycięcie,
    więc sam prostokąt obrazu bywa większy niż strona. Widoczną część bierzemy
    z dziennika rysowania (bboxlog), który uwzględnia przycięcie.
    """
    infos = page.get_image_info(xrefs=True)
    visible = []
    try:
        visible = [fitz.Rect(r) for t, r in page.get_bboxlog() if t in ("fill-image", "fill-imgmask")]
    except Exception:
        visible = []
    out = []
    for i, info in enumerate(infos):
        r = fitz.Rect(info["bbox"]) & page.rect
        if len(visible) == len(infos):
            r = visible[i] & page.rect
        out.append((info.get("xref", 0), r, info))
    return out


def _is_photo(doc, xref) -> bool:
    """Czy obraz w PDF to zdjęcie osoby (a nie logo / grafika)."""
    try:
        from PIL import Image
        from .photo import looks_like_photo
        pix = fitz.Pixmap(doc, xref)
        if pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        if pix.n not in (1, 3):
            pix = fitz.Pixmap(fitz.csRGB, pix)
        mode = "L" if pix.n == 1 else "RGB"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        return looks_like_photo(img)
    except Exception:
        return False


def _remove_photos(page) -> int:
    pr = page.rect
    n = 0
    deleted = set()
    redact = []
    for xref, r, info in _visible_image_rects(page):
        if r.is_empty or r.width < 30 or r.height < 30:
            continue  # ikonki
        if r.get_area() > 0.5 * pr.get_area():
            continue  # tło strony
        if r.height > 3 * r.width or r.width > 3 * r.height:
            continue  # pasek / ozdobnik, nie zdjęcie
        if not xref or not _is_photo(page.parent, xref):
            continue  # logo, ikona, element oprawy graficznej - zostaje
        if xref not in deleted:
            try:
                page.delete_image(xref)  # usuwa dane obrazu, także niewidoczną (przyciętą) część
                deleted.add(xref)
                n += 1
                continue
            except Exception:
                pass
        redact.append(r)  # nie udało się usunąć danych obrazu - zamaż piksele
    for r in redact:
        page.add_redact_annot(r, fill=(1, 1, 1))
        n += 1
    if redact:
        _apply(page, _redact_images_mode())
    # miniaturka strony (niektóre programy ją zapisują)
    try:
        doc = page.parent
        if "Thumb" in doc.xref_get_keys(page.xref):
            doc.xref_set_key(page.xref, "Thumb", "null")
    except Exception:
        pass
    return n


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
        # 1) zdjęcia: każdy obraz, który nie jest tłem strony - usuwany razem z danymi
        if remove_photos:
            stats["zdjecia"] += _remove_photos(page)

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

    n_pages = doc.page_count
    _save_safely(doc, out_path, n_pages)
    doc.close()
    return stats


# --- bezpieczny zapis ---------------------------------------------------------

def pdf_ok(path: str, n_pages: int | None = None) -> bool:
    """Czy PDF da się otworzyć i wyrenderować każdą stronę (bez "naprawiania" po drodze)."""
    import os
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    try:
        fitz.TOOLS.mupdf_warnings(reset=True)
    except Exception:
        pass
    try:
        with fitz.open(path) as d:
            if d.is_repaired if hasattr(d, "is_repaired") else False:
                return False
            if n_pages is not None and d.page_count != n_pages:
                return False
            if d.page_count == 0:
                return False
            for page in d:
                page.get_pixmap(dpi=20)
                page.get_text("text")
        try:
            w = fitz.TOOLS.mupdf_warnings(reset=True) or ""
            if "repair" in w.lower() or "syntax error" in w.lower():
                return False
        except Exception:
            pass
    except Exception:
        return False
    return _qpdf_ok(path, n_pages)


def _qpdf_ok(path: str, n_pages: int | None) -> bool:
    """Druga, niezależna kontrola: qpdf (ten sam rodzaj ścisłości co Adobe Reader)."""
    try:
        import pikepdf
    except ImportError:
        return True
    try:
        with pikepdf.open(path) as p:
            if n_pages is not None and len(p.pages) != n_pages:
                return False
            warn = " ".join(str(w) for w in (p.get_warnings() if hasattr(p, "get_warnings") else []))
            if "damaged" in warn.lower() or "recover" in warn.lower():
                return False  # qpdf musiał "naprawiać" plik - Adobe Reader może go odrzucić
            check = getattr(p, "check_pdf_syntax", None) or getattr(p, "check", None)
            if check is not None:
                problems = [x for x in check() if "error" in str(x).lower()]
                if problems:
                    return False
            return True
    except Exception:
        return False


def normalize(path: str, n_pages: int | None = None) -> None:
    """Przepisuje PDF przez qpdf do ściśle zgodnej ze standardem postaci
    (czytelnej dla Adobe Readera). Usuwa też wszystkie nieużywane obiekty."""
    import os
    try:
        import pikepdf
    except ImportError:
        return
    tmp = path + ".qpdf"
    try:
        with pikepdf.open(path) as p:
            p.save(tmp)
        if pdf_ok(tmp, n_pages):
            os.replace(tmp, path)
    except Exception:
        pass
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _save_safely(doc, out_path: str, n_pages: int) -> None:
    """Zapis z kontrolą: kilka coraz ostrożniejszych sposobów, aż wynik będzie poprawny."""
    attempts = [dict(garbage=3, deflate=True), dict(garbage=1, deflate=True), dict(garbage=0)]
    for opts in attempts:
        try:
            doc.save(out_path, **opts)
        except Exception:
            continue
        if pdf_ok(out_path, n_pages):
            normalize(out_path, n_pages)
            return
    raise RuntimeError("Nie udało się zapisać poprawnego pliku PDF. Oryginał jest nietknięty - "
                       "spróbuj wyłączyć „Usuń zdjęcie kandydata” albo zamazać zdjęcie ręcznie.")
