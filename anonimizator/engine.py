"""Wspólny interfejs: odczyt, wykrywanie, anonimizacja i kontrola wyniku."""
from __future__ import annotations

from pathlib import Path

from .detector import Finding, build_pattern, detect

IMAGES = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".tif": "TIFF", ".tiff": "TIFF",
          ".bmp": "BMP", ".webp": "WebP"}
SUPPORTED = {".pdf": "PDF", ".docx": "Word", ".txt": "Tekst", **IMAGES}


class UnsupportedFile(Exception):
    pass


def _handler(path: str):
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        from . import pdf_handler
        return pdf_handler
    if ext == ".docx":
        from . import docx_handler
        return docx_handler
    if ext == ".txt":
        from . import txt_handler
        return txt_handler
    if ext in IMAGES:
        from . import image_handler
        return image_handler
    if ext == ".doc":
        raise UnsupportedFile("Stary format .doc nie jest obsługiwany. Otwórz plik w Wordzie "
                              "i zapisz jako .docx (Plik → Zapisz jako → Dokument programu Word).")
    raise UnsupportedFile(f"Nieobsługiwany format pliku: {ext or '(brak)'}. Obsługiwane: PDF, DOCX, TXT, JPG, PNG, TIFF, BMP.")


def extract_lines(path: str) -> list[str]:
    return _handler(path).extract_lines(path)


def warnings_for(path: str) -> list[str]:
    out = []
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        from .pdf_handler import scanned_pages
        if scanned_pages(path):
            out.append("Ten PDF to skan - tekst jest odczytywany przez OCR, co może nie być idealne. "
                       "Sprawdź podgląd. Zdjęcie kandydata zaznacz przyciskiem „Zamaż obszar…”.")
    elif ext in IMAGES:
        out.append("Obrazek - tekst odczytano przez OCR, więc sprawdź podgląd. Zdjęcie kandydata "
                   "sprawdź (lub zaznacz) przyciskiem „Zamaż obszar…”.")
    return out


def suggest_areas(path: str) -> list[tuple]:
    """Automatycznie wykryte zdjęcie (dla obrazków i skanów) - jako propozycja."""
    if not supports_areas(path):
        return []
    try:
        return _handler(path).suggest_areas(path)
    except Exception:
        return []


def supports_areas(path: str) -> bool:
    """Czy dla tego pliku można ręcznie zaznaczać obszary do zamazania."""
    ext = Path(path).suffix.lower()
    return ext == ".pdf" or ext in IMAGES


def analyze(path: str) -> tuple[list[str], list[Finding]]:
    lines = extract_lines(path)
    titles = None
    h = _handler(path)
    if hasattr(h, "title_lines"):
        try:
            titles = h.title_lines(path)
        except Exception:
            titles = None
    return lines, detect(lines, Path(path).name, titles)


def anonymize(path: str, out_path: str, findings: list[Finding], blackout: bool = False,
              remove_photos: bool = True, manual=None) -> dict:
    """manual: ręcznie zaznaczone obszary [(strona, x0, y0, x1, y1)] we współrzędnych 0-1."""
    if Path(path).resolve() == Path(out_path).resolve():
        raise ValueError("Plik wynikowy nie może nadpisać oryginału.")
    import os
    kw = {"manual": manual} if supports_areas(path) else {}
    final = Path(out_path)
    # zapis do pliku tymczasowego obok - właściwy plik pojawia się dopiero, gdy wszystko jest w porządku
    tmp = final.with_name(f"~{final.stem}.tmp{final.suffix}")
    try:
        stats = _handler(path).anonymize(path, str(tmp), findings, blackout=blackout,
                                          remove_photos=remove_photos, **kw)
        if _uses_ocr(path):
            extra = []
            for _ in range(2):  # najwyżej dwie dodatkowe rundy, tylko jeśli coś się znajduje
                new = _second_pass(str(tmp), findings, blackout)
                if not new:
                    break
                extra += new
            stats["dodatkowo"] = extra
            stats["zamiany"] += len(extra)
        _validate(str(tmp))
        os.replace(tmp, final)
    finally:
        if tmp.exists():
            tmp.unlink()
    stats["pozostalo"] = verify(str(final), findings)
    return stats


def _validate(path: str) -> None:
    """Czy plik wynikowy da się otworzyć. Jeśli nie - błąd zamiast uszkodzonego pliku."""
    import os
    import zipfile
    ext = Path(path).suffix.lower()
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise RuntimeError("Plik wynikowy jest pusty - zapis się nie udał.")
    if ext == ".pdf":
        from .pdf_handler import pdf_ok
        if not pdf_ok(path):
            raise RuntimeError("Plik wynikowy PDF jest uszkodzony - nie został zapisany.")
    elif ext == ".docx":
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:
                raise RuntimeError("Plik wynikowy Word jest uszkodzony - nie został zapisany.")
        from docx import Document
        Document(path)
    elif ext in IMAGES:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()


def candidate_summary(findings: list[Finding]) -> dict:
    """Dane do listy kandydatów (zostaje u użytkownika): imię i nazwisko, telefon, e-mail."""
    def first(kind_prefix, prefer_long=False):
        xs = [f.text for f in findings if f.enabled and f.kind.startswith(kind_prefix)]
        if not xs:
            return ""
        if prefer_long:
            multi = [x for x in xs if len(x.split()) >= 2] or xs
            return max(multi, key=len)
        return xs[0]
    name = first("Imię", prefer_long=True)
    if name.isupper():
        name = name.title()
    return {"imie_nazwisko": name, "telefon": first("Telefon"), "email": first("E-mail")}


def _uses_ocr(path: str) -> bool:
    ext = Path(path).suffix.lower()
    if ext in IMAGES:
        return True
    if ext == ".pdf":
        from .pdf_handler import scanned_pages
        return bool(scanned_pages(path))
    return False


# kategorie, które kolejna runda może dopisać sama (nazwiska tylko przez kandydata z 1. rundy)
_SECOND_PASS_KINDS = {"E-mail", "Telefon", "PESEL / dokument", "Profil / link", "Data / miejsce urodzenia",
                      "Adres", "Kod pocztowy / miasto"}


def _second_pass(out_path: str, findings: list[Finding], blackout: bool) -> list[str]:
    """OCR wyniku jeszcze raz: po zamazaniu części tekstu reszta czyta się często lepiej.

    Zamazuje dane wykryte dopiero teraz (e-mail, telefon, link...), z pominięciem tego,
    co użytkownik świadomie odznaczył.
    """
    import os
    import shutil
    import tempfile
    disabled = {f.key for f in findings if not f.enabled}
    known = {f.key for f in findings}
    lines = extract_lines(out_path)
    cand = [f for f in findings if f.enabled and f.kind.startswith("Imię")]
    name = max((f.text for f in cand), key=len, default=None)
    new = []
    for f in detect(lines, None, candidate=name):
        if f.key in known or f.key in disabled or "[" in f.text:
            continue
        if f.kind in _SECOND_PASS_KINDS:
            new.append(f)
    if not new:
        return []
    fd, tmp = tempfile.mkstemp(suffix=Path(out_path).suffix)
    os.close(fd)
    try:
        _handler(out_path).anonymize(out_path, tmp, new + cand, blackout=blackout, remove_photos=False)
        shutil.move(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    findings.extend(new)  # żeby weryfikacja też je sprawdziła
    return [f.text for f in new]


def verify(out_path: str, findings: list[Finding]) -> list[str]:
    """Sprawdza, czy w pliku wynikowym nie zostały zaznaczone dane."""
    text = "\n".join(extract_lines(out_path))
    left = []
    for f in findings:
        if f.enabled and build_pattern(f).search(text):
            left.append(f.text)
    return left


def default_output_name(path: str) -> str:
    """Nazwa wyniku BEZ imienia i nazwiska (oryginalne nazwy plików często je zawierają)."""
    from datetime import datetime
    p = Path(path)
    return f"CV_anonim_{datetime.now():%Y%m%d_%H%M%S}{p.suffix.lower()}"


def render_pages(path: str, max_pages: int = 10, dpi: int = 110):
    """Obrazy stron (PIL) do ręcznego zaznaczania obszarów."""
    ext = Path(path).suffix.lower()
    if ext in IMAGES:
        from .image_handler import load_image
        return [load_image(path).convert("RGB")]
    from PIL import Image
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    out = []
    with fitz.open(path) as doc:
        for page in list(doc)[:max_pages]:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            out.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return out


# --- gdzie zapisywać wyniki ----------------------------------------------------
# Windows (a za nim Adobe Reader i Excel) nie otwiera plików ze ścieżką dłuższą niż 260 znaków.
# Dlatego wyniki NIE trafiają obok oryginałów (te bywają głęboko w OneDrive/Outlooku),
# tylko do krótkiej, stałej ścieżki w Dokumentach.
MAX_SAFE_PATH = 200


def documents_dir() -> Path:
    """Folder Dokumenty użytkownika (także przekierowany do OneDrive)."""
    import os
    import sys
    if sys.platform.startswith("win"):
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except Exception:
            pass
        prof = os.environ.get("USERPROFILE")
        if prof and (Path(prof) / "Documents").is_dir():
            return Path(prof) / "Documents"
    home = Path.home()
    return home / "Documents" if (home / "Documents").is_dir() else home


def results_root() -> Path:
    root = documents_dir() / "CV zanonimizowane"
    if len(str(root)) > MAX_SAFE_PATH - 60:
        root = Path(Path.home().anchor or "/") / "CV zanonimizowane"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_batch_dir() -> Path:
    """Osobny folder dla każdej partii CV, np. ...\\CV zanonimizowane\\2026-11-23 16.50"""
    from datetime import datetime
    root = results_root()
    base = datetime.now().strftime("%Y-%m-%d %H.%M")
    d, n = root / base, 2
    while d.exists():
        d, n = root / f"{base} ({n})", n + 1
    d.mkdir(parents=True)
    return d


LIST_HEADER = ["plik zanonimizowany", "imię i nazwisko", "telefon", "e-mail",
               "plik oryginalny", "folder oryginału", "data", "uwagi"]


def write_candidate_list(out_dir, src: str, out, note: str = "", findings=None):
    """Lista "który numer to który kandydat" - zostaje u użytkownika, nigdy nie jest wysyłana."""
    import csv
    from datetime import datetime
    info = candidate_summary(findings or [])
    lst = out_dir / "lista_kandydatow.csv"
    new = not lst.exists()
    with open(lst, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if new:
            w.writerow(LIST_HEADER)
        w.writerow([out.name if out else "(nie zapisano)", info["imie_nazwisko"] or "(nie wykryto)",
                    info["telefon"], info["email"], Path(src).name, str(Path(src).parent),
                    f"{datetime.now():%Y-%m-%d %H:%M}", note])
