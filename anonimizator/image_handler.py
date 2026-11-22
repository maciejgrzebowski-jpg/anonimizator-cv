"""CV w postaci obrazka (JPG, PNG...): OCR -> wykrycie danych -> zamalowanie na obrazku."""
from __future__ import annotations

import os
from collections import Counter

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import ocr
from .detector import Finding

_CACHE: dict = {}

FONT_CANDIDATES = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
                   "/System/Library/Fonts/Supplemental/Arial.ttf",
                   "/Library/Fonts/Arial.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def load_image(path: str) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # zdjęcia z telefonu bywają obrócone
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def words(path: str):
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size)
    if key not in _CACHE:
        _CACHE[key] = ocr.ocr_words(load_image(path))
    return _CACHE[key]


def extract_lines(path: str) -> list[str]:
    return ocr.words_to_lines(words(path))


def title_lines(path: str) -> list[tuple]:
    return ocr.title_lines(words(path))


def _font(size: int):
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _background(img, box):
    """Najczęstszy kolor na obrzeżu pola - żeby łata wtapiała się w tło."""
    x0, y0, x1, y1 = box
    rgb = img.convert("RGB")
    pts = []
    for x in range(max(0, x0), min(img.width, x1), 2):
        for y in (max(0, y0 - 1), min(img.height - 1, y1 + 1)):
            pts.append(rgb.getpixel((x, y)))
    for y in range(max(0, y0), min(img.height, y1), 2):
        for x in (max(0, x0 - 1), min(img.width - 1, x1 + 1)):
            pts.append(rgb.getpixel((x, y)))
    if not pts:
        return (255, 255, 255)
    # zaokrąglamy, żeby szum JPEG nie rozbijał kolorów
    bucket = Counter(tuple(v // 16 for v in p) for p in pts).most_common(1)[0][0]
    same = [p for p in pts if tuple(v // 16 for v in p) == bucket]
    return tuple(round(sum(p[i] for p in same) / len(same)) for i in range(3))


def paint(img: Image.Image, boxes, blackout: bool) -> Image.Image:
    """boxes: (x0, y0, x1, y1, etykieta[, margines]) w pikselach."""
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)
    for b in boxes:
        x0, y0, x1, y1, label = b[:5]
        pad = max(2, round((y1 - y0) * 0.12)) if len(b) < 6 or b[5] else 0
        box = (int(x0) - pad, int(y0) - pad, int(x1) + pad, int(y1) + pad)
        if blackout:
            d.rectangle(box, fill=(0, 0, 0))
            continue
        bg = _background(img, box)
        d.rectangle(box, fill=bg)
        if not label:
            continue
        lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        fg = (0, 0, 0) if lum > 140 else (255, 255, 255)
        h = box[3] - box[1]
        w = box[2] - box[0]
        size = max(8, min(int(h * 0.75), 36))
        font = _font(size)
        while size > 8 and d.textlength(label, font=font) > w:
            size -= 1
            font = _font(size)
        if d.textlength(label, font=font) > w:
            label = "***"
        d.text((box[0], box[1] + h / 2), label, fill=fg, font=font, anchor="lm")
    return img


def manual_to_pixels(manual, width, height, page=0):
    """Ręcznie zaznaczone obszary (ułamki 0-1) -> piksele."""
    out = []
    for p, fx0, fy0, fx1, fy1 in manual or []:
        if p == page:
            out.append((fx0 * width, fy0 * height, fx1 * width, fy1 * height, "[ZDJECIE]", False))
    return out


def anonymize(path: str, out_path: str, findings: list[Finding], blackout: bool = False,
              remove_photos: bool = True, manual=None) -> dict:
    img = load_image(path)
    hits = ocr.match_boxes(words(path), findings)
    boxes = [(x0, y0, x1, y1, label) for x0, y0, x1, y1, label, _ in hits]
    boxes += manual_to_pixels(manual, img.width, img.height)
    out = paint(img, boxes, blackout)
    fmt = (Image.registered_extensions().get(os.path.splitext(out_path)[1].lower()) or "PNG")
    kw = {"quality": 92} if fmt == "JPEG" else {}
    out.save(out_path, fmt, **kw)  # zapis bez EXIF (bez GPS, daty, modelu telefonu)
    return {"zamiany": len(hits), "zdjecia": len(manual or []), "linki": 0}


def detect_photos(img: Image.Image, words) -> list[tuple]:
    """Szuka zdjęcia kandydata: zwarty, wypełniony prostokąt bez tekstu.

    Proste reguły (bez AI) - wynik to propozycja, użytkownik ją widzi i może poprawić.
    Zwraca obszary jako ułamki (x0, y0, x1, y1).
    """
    W = 240
    k = W / img.width
    H = max(1, round(img.height * k))
    small = img.convert("RGB").resize((W, H))
    px = small.load()
    q = [[tuple(v // 24 for v in px[x, y]) for x in range(W)] for y in range(H)]
    text = [[False] * W for _ in range(H)]
    for x0, y0, x1, y1, *_ in words:
        for y in range(max(0, int(y0 * k) - 1), min(H, int(y1 * k) + 2)):
            for x in range(max(0, int(x0 * k) - 1), min(W, int(x1 * k) + 2)):
                text[y][x] = True
    # tło może mieć kilka kolorów (biała strona, kolorowy pasek nagłówka) - sprawdzamy każdy
    counts = Counter(c for row in q for c in row)
    found: list = []
    for bg, cnt in counts.most_common(3):
        if cnt < 0.05 * W * H:
            break
        mask = [[q[y][x] != bg and not text[y][x] for x in range(W)] for y in range(H)]
        for b in _blobs(mask, W, H):
            if not any(_iou(b, f) > 0.3 for f in found):
                found.append(b)
    return found[:2]


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0


def _blobs(mask, W, H):
    seen = [[False] * W for _ in range(H)]
    found = []
    for sy in range(H):
        for sx in range(W):
            if not mask[sy][sx] or seen[sy][sx]:
                continue
            stack = [(sx, sy)]
            seen[sy][sx] = True
            n, minx, miny, maxx, maxy = 0, sx, sy, sx, sy
            while stack:
                x, y = stack.pop()
                n += 1
                minx, maxx, miny, maxy = min(minx, x), max(maxx, x), min(miny, y), max(maxy, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < W and 0 <= ny < H and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            bw, bh = maxx - minx + 1, maxy - miny + 1
            if not (0.08 * W <= bw <= 0.45 * W and 0.05 * H <= bh <= 0.40 * H):
                continue
            if not (0.6 <= bh / bw <= 2.2) or n / (bw * bh) < 0.55:
                continue
            # zdjęcie zwykle jest w górnej połowie strony
            if miny > 0.5 * H:
                continue
            found.append((max(0, minx - 2) / W, max(0, miny - 2) / H,
                          min(W, maxx + 3) / W, min(H, maxy + 3) / H))
    return found


def suggest_areas(path: str) -> list[tuple]:
    img = load_image(path)
    return [(0, *b) for b in detect_photos(img, words(path))]
