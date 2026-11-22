"""Pobiera pliki językowe do rozpoznawania tekstu (OCR): polski i angielski.

Uruchom raz (potrzebny internet tylko teraz):  python pobierz_ocr.py
Pliki trafiają do anonimizator/data/tessdata i są dołączane do instalatora.
Program potem działa w pełni offline.
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

URL = "https://github.com/tesseract-ocr/tessdata_best/raw/main/{}.traineddata"
DEST = Path(__file__).resolve().parent / "anonimizator" / "data" / "tessdata"
LANGS = ["pol", "eng"]


def download(url: str, target: Path):
    tmp = target.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:  # np. brak certyfikatów w Pythonie z python.org na Macu
        if shutil.which("curl"):
            print(f"  (urllib: {e.__class__.__name__}, próbuję przez curl)")
            subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(tmp), url], check=True)
        else:
            raise
    tmp.replace(target)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    DEST.mkdir(parents=True, exist_ok=True)
    for lang in LANGS:
        target = DEST / f"{lang}.traineddata"
        if target.exists() and target.stat().st_size > 1_000_000:
            print(f"{target.name}: już jest")
            continue
        print(f"Pobieram {target.name}…")
        download(URL.format(lang), target)
        print(f"  OK ({target.stat().st_size // 1_000_000} MB)")
    print("Gotowe. OCR będzie działał offline.")


if __name__ == "__main__":
    sys.exit(main())
