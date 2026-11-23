"""Czy obraz to zdjęcie osoby, czy logo/grafika? Proste reguły na kolorach, bez AI."""
from __future__ import annotations

from PIL import Image


def _skin(r: int, g: int, b: int) -> bool:
    """Kolor skóry wg składowych chrominancji (Cb, Cr) - niezależnie od jasności,
    więc działa dla jasnej i ciemnej karnacji (reguła Chai & Ngan)."""
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return 77 <= cb <= 127 and 133 <= cr <= 173 and (r + g + b) > 60


def photo_stats(img: Image.Image) -> dict:
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("RGB")
    w, h = img.size
    small = img.copy()
    small.thumbnail((96, 96))
    getter = getattr(small, "get_flattened_data", None) or small.getdata
    px = list(getter())
    n = len(px) or 1
    colors = len({(r >> 3, g >> 3, b >> 3) for r, g, b in px})
    skin = sum(_skin(*p) for p in px) / n
    sat = sum(max(p) - min(p) for p in px) / n
    grays = len({(r + g + b) // 3 >> 1 for r, g, b in px})
    lum = [(r + g + b) / 3 for r, g, b in px]
    mean = sum(lum) / n
    std = (sum((v - mean) ** 2 for v in lum) / n) ** 0.5
    return {"w": w, "h": h, "colors": colors, "skin": skin, "sat": sat, "grays": grays, "std": std}


def looks_like_photo(img: Image.Image) -> bool:
    s = photo_stats(img)
    if s["w"] < 24 or s["h"] < 24:
        return False
    aspect = s["h"] / s["w"]
    if not 0.5 <= aspect <= 2.0:
        return False  # paski, banery
    if s["sat"] < 12:  # obraz czarno-biały
        return s["grays"] >= 70 and s["std"] > 25
    return (s["colors"] >= 200 and s["skin"] >= 0.03) or s["colors"] >= 600


def fake_portrait(w: int = 300, h: int = 380, seed: int = 1) -> Image.Image:
    """Syntetyczne "zdjęcie" do testów: gradientowe tło, twarz w kolorze skóry, szum jak w aparacie."""
    import random
    from PIL import ImageDraw, ImageFilter
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (150 + x * 60 // w, 170 + y * 40 // h, 200 - y * 30 // h)
    d = ImageDraw.Draw(img)
    for i in range(12):  # cieniowanie twarzy
        c = (225 - i * 4, 180 - i * 4, 150 - i * 4)
        o = i * w * 0.006
        d.ellipse((w * 0.3 + o, h * 0.15 + o, w * 0.7 - o, h * 0.6 - o), fill=c)
    d.rectangle((w * 0.15, h * 0.68, w * 0.85, h), fill=(50, 70, 120))
    for _ in range(400):  # faktura: włosy, ubranie, tło
        x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(2, 9)
        base = px[min(x, w - 1), min(y, h - 1)]
        c = tuple(max(0, min(255, v + rnd.randint(-45, 45))) for v in base)
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    px = img.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            n = rnd.randint(-22, 22)
            px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return img
