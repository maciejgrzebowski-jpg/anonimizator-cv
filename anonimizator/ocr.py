"""Rozpoznawanie tekstu (OCR) - lokalnie, bez internetu.

Kolejność wyboru silnika:
  1. program Tesseract dołączony do instalatora Windows (folder "tesseract" obok programu)
     albo zainstalowany w systemie (np. `brew install tesseract` na Macu) - najlepsze wyniki,
  2. awaryjnie: silnik Tesseract wbudowany w PyMuPDF.
Pliki językowe (polski, angielski) są brane z anonimizator/data/tessdata, jeśli istnieją.

Wynik: lista słów (x0, y0, x1, y1, tekst, klucz_linii) we współrzędnych pikseli obrazu.
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .detector import _data_dir

LANG = "pol+eng"
TARGET_WIDTH = 2500        # typowe skany powiększamy do tej szerokości
SMALL_TARGET_WIDTH = 3200  # bardzo małe obrazki (np. z internetu) - mocniej


class OcrUnavailable(Exception):
    pass


def tessdata_dir() -> Path | None:
    d = _data_dir() / "tessdata"
    if (d / "pol.traineddata").exists() and (d / "eng.traineddata").exists():
        return d
    return None


def _has_pymupdf() -> bool:
    try:
        import pymupdf  # noqa: F401
        return True
    except ImportError:
        try:
            import fitz  # noqa: F401
            return True
        except ImportError:
            return False


def tesseract_exe() -> str | None:
    """Szuka programu tesseract: obok aplikacji, w zmiennej środowiskowej, w systemie."""
    cands = [os.environ.get("ANONIMIZATOR_TESSERACT")]
    exe_dir = Path(sys.executable).resolve().parent
    name = "tesseract.exe" if sys.platform.startswith("win") else "tesseract"
    cands += [str(exe_dir / "tesseract" / name), shutil.which("tesseract")]
    if sys.platform.startswith("win"):
        cands.append(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    else:
        cands += ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract"]
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


def backend() -> str:
    forced = os.environ.get("ANONIMIZATOR_OCR")
    if forced in ("pymupdf", "cli"):
        return forced
    if tesseract_exe():
        return "cli"
    if tessdata_dir() and _has_pymupdf():
        return "pymupdf"
    raise OcrUnavailable(
        "Brak programu do rozpoznawania tekstu (OCR). Na Macu: brew install tesseract "
        "albo uruchom raz: python pobierz_ocr.py")


def _invert_dark(g):
    """Jasny tekst na ciemnym tle (kolorowe paski boczne) -> ciemny na jasnym.

    OCR czyta wyraźnie lepiej, gdy cała strona ma jedną "polaryzację".
    """
    from PIL import Image, ImageFilter, ImageOps
    # mapa "ciemnych" pikseli, uśredniona w szerokim otoczeniu (ok. 3% szerokości strony);
    # dzięki temu grube białe litery na ciemnym tle nie "dziurawią" maski
    small_w = 400
    k = small_w / g.width
    small = g.resize((small_w, max(1, round(g.height * k))))
    dark = small.point(lambda v: 255 if v < 110 else 0)
    frac = dark.filter(ImageFilter.BoxBlur(8))
    # tylko obszary prawie w całości ciemne (tło paska), nie duże ciemne litery
    mask = frac.point(lambda v: 255 if v > 185 else 0).resize(g.size)
    if not mask.getbbox():
        return g
    return Image.composite(ImageOps.invert(g), g, mask)


def _prepare(img):
    """Szarość, kontrast, powiększenie, wyrównanie tła. Zwraca (obraz, skala)."""
    from PIL import Image, ImageOps
    g = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
    target = SMALL_TARGET_WIDTH if g.width < 1000 else TARGET_WIDTH
    scale = 1.0
    if g.width < target:
        scale = target / g.width
        g = g.resize((round(g.width * scale), round(g.height * scale)), Image.LANCZOS)
    return g, scale


def _ocr_cli(g):
    buf = io.BytesIO()
    g.save(buf, "PNG")
    flags = {}
    if sys.platform.startswith("win"):
        flags["creationflags"] = 0x08000000  # bez czarnego okna konsoli
    cmd = [tesseract_exe() or "tesseract", "stdin", "stdout"]
    td = tessdata_dir()
    if td:
        cmd += ["--tessdata-dir", str(td)]
    # "-c tessedit_create_tsv=1" zamiast "tsv" - działa bez plików configs w tessdata
    cmd += ["-l", LANG, "--psm", "3", "-c", "tessedit_create_tsv=1"]
    res = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, **flags)
    if res.returncode != 0:
        raise RuntimeError("Tesseract: " + res.stderr.decode("utf-8", "replace")[-500:])
    words = []
    rows = csv.DictReader(io.StringIO(res.stdout.decode("utf-8", "replace")), delimiter="\t",
                          quoting=csv.QUOTE_NONE)
    for r in rows:
        txt = (r.get("text") or "").strip()
        if r.get("level") != "5" or not txt:
            continue
        x, y, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
        key = (int(r["block_num"]), int(r["par_num"]), int(r["line_num"]))
        try:
            conf = float(r.get("conf") or 0)
        except ValueError:
            conf = 0.0
        words.append((x, y, x + w, y + h, txt, key, conf))
    return words


def _ocr_pymupdf(g):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    buf = io.BytesIO()
    g.save(buf, "PNG")
    with fitz.open(stream=buf.getvalue(), filetype="png") as imgdoc:
        pdf = fitz.open(stream=imgdoc.convert_to_pdf(), filetype="pdf")
    page = pdf[0]
    k = g.width / page.rect.width  # punkty PDF -> piksele
    tp = page.get_textpage_ocr(language=LANG, dpi=round(72 * k), full=True,
                               tessdata=str(tessdata_dir()))
    words = []
    for x0, y0, x1, y1, txt, b, l, _ in page.get_text("words", textpage=tp):
        words.append((x0 * k, y0 * k, x1 * k, y1 * k, txt, (b, l), 50.0))
    pdf.close()
    return words


def _overlap(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1
    return ix * iy / small


def _merge(normal, negative):
    """Łączy odczyt zwykły i z negatywu: w każdym miejscu wygrywa pewniejsze słowo.

    Negatyw dobrze czyta jasny tekst na ciemnym tle (kolorowe paski, nagłówki).
    """
    keep = list(normal)
    for nw in negative:
        if nw[6] < 60:
            continue
        hits = [i for i, w in enumerate(keep) if w is not None and _overlap(w, nw) > 0.3]
        best = max((keep[i][6] for i in hits), default=-1)
        if nw[6] > best + 10:
            for i in hits:
                keep[i] = None
            keep.append(nw)
    return [w for w in keep if w is not None]


def ocr_words(img):
    """OCR obrazu PIL. Zwraca słowa (x0, y0, x1, y1, tekst, linia) we współrzędnych obrazu."""
    from PIL import ImageOps
    g, scale = _prepare(img)
    if backend() == "cli":
        normal = _ocr_cli(g)
        words = normal
        # drugi odczyt (negatyw) tylko, gdy na stronie są ciemne obszary - oszczędza czas
        hist = g.histogram()
        if sum(hist[:110]) > 0.04 * g.width * g.height:
            negative = [(*w[:5], ("neg",) + tuple(w[5]), w[6]) for w in _ocr_cli(ImageOps.invert(g))]
            words = _merge(normal, negative)
    else:
        words = _ocr_pymupdf(g)
    return [(w[0] / scale, w[1] / scale, w[2] / scale, w[3] / scale, w[4], w[5]) for w in words]


def title_lines(words) -> list[tuple]:
    """Linie posortowane od największego napisu: (wysokość, pozycja_y, tekst).

    Imię i nazwisko to zwykle największy napis w CV - niezależnie od układu strony.
    """
    lines: dict = {}
    for w in words:
        lines.setdefault(w[5], []).append(w)
    out = []
    for ws in lines.values():
        hs = sorted(w[3] - w[1] for w in ws)
        out.append((hs[len(hs) // 2], min(w[1] for w in ws), " ".join(w[4] for w in ws)))
    return sorted(out, key=lambda t: -t[0])


def words_to_lines(words) -> list[str]:
    lines: dict = {}
    for w in words:
        lines.setdefault(w[5], []).append(w[4])
    return [" ".join(v) for v in lines.values()]


def match_boxes(words, findings):
    """Dopasowuje znaleziska do słów z OCR.

    Zwraca listę (x0, y0, x1, y1, etykieta, czy_pierwszy_fragment).
    Działa na całych liniach, więc łapie też wielowyrazowe dane (adres, telefon).
    """
    from .detector import build_pattern
    lines: dict = {}
    for i, w in enumerate(words):
        lines.setdefault(w[5], []).append(i)
    used: set = set()
    out = []
    for f in findings:  # od najdłuższych
        if not f.enabled:
            continue
        rx = build_pattern(f)
        for idxs in lines.values():
            text, spans = "", []
            for i in idxs:
                if text:
                    text += " "
                spans.append((len(text), len(text) + len(words[i][4]), i))
                text += words[i][4]
            for m in rx.finditer(text):
                hit = [i for s, e, i in spans if s < m.end() and e > m.start() and i not in used]
                if not hit:
                    continue
                used.update(hit)
                x0 = min(words[i][0] for i in hit)
                y0 = min(words[i][1] for i in hit)
                x1 = max(words[i][2] for i in hit)
                y1 = max(words[i][3] for i in hit)
                out.append((x0, y0, x1, y1, f.replacement, True))
    return out
