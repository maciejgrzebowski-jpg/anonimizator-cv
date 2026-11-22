"""Anonimizacja zwykłych plików tekstowych."""
from __future__ import annotations

from .detector import Finding, build_pattern

BLACKOUT = "█████"
ENCODINGS = ("utf-8-sig", "cp1250", "latin-1")


def _read(path: str) -> tuple[str, str]:
    raw = open(path, "rb").read()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def extract_lines(path: str) -> list[str]:
    return _read(path)[0].splitlines()


def anonymize(path: str, out_path: str, findings: list[Finding], blackout: bool = False,
              remove_photos: bool = True) -> dict:
    text, enc = _read(path)
    n = 0
    for f in findings:
        if not f.enabled:
            continue
        repl = BLACKOUT if blackout else f.replacement
        text, k = build_pattern(f).subn(lambda m: repl, text)
        n += k
    with open(out_path, "w", encoding="utf-8" if enc == "utf-8-sig" else enc, errors="replace") as fh:
        fh.write(text)
    return {"zamiany": n, "zdjecia": 0, "linki": 0}
