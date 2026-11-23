"""Testy: python -m pytest -q"""
import importlib.util
from pathlib import Path

import pytest

from anonimizator import engine
from anonimizator.detector import KANDYDAT, OSOBA, detect

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "przyklady"
SECRETS = ["Katarzyn", "Wiśniewsk", "Kwiatowa", "31-512", "602 345 678",
           "k.wisniewska.lis@example.com", "linkedin.com/in", "14.05.1991",
           "Tomasz Zieliński", "501 222 333"]
KEEP = ["Uniwersytet Jagielloński", "Specjalistka ds. rekrutacji", "Firma ABC", "Katowice"]

HAS_PYMUPDF = importlib.util.find_spec("pymupdf") or importlib.util.find_spec("fitz")


# --- wykrywanie ---------------------------------------------------------------

def kinds(lines, fn=None):
    return {(f.kind, f.text) for f in detect(lines, fn)}


def test_basic_fields():
    lines = ["Jan Kowalski", "ul. Długa 5, 00-950 Warszawa", "+48 601 234 567",
             "jan.k@example.pl", "PESEL: 44051401359", "github.com/jankow"]
    texts = {t for _, t in kinds(lines)}
    for x in ["Jan Kowalski", "Kowalski", "ul. Długa 5", "00-950 Warszawa", "+48 601 234 567",
              "jan.k@example.pl", "44051401359", "github.com/jankow"]:
        assert x in texts, x
    # "Jan" samo w sobie jest niejednoznaczne (ang. styczeń) - nie zamieniamy wszędzie
    assert "Jan" not in texts


def test_no_false_positives_on_dates_and_years():
    lines = ["Anna Nowak", "01.2019 - 05.2021 Kierownik", "2015-2018 Politechnika Warszawska",
             "Obroty 1 200 000 zł"]
    texts = {t for _, t in kinds(lines)}
    assert not any("2019" in t or "2015" in t for t in texts)


def test_name_from_header_without_dictionary():
    lines = ["Zbyszko Bogdanowicz", "Doświadczenie"]  # "Zbyszko" nie ma w słowniku
    assert (KANDYDAT, "Zbyszko Bogdanowicz") in kinds(lines)


def test_name_from_filename():
    lines = ["CURRICULUM VITAE", "Doświadczenie", "Kontakt: 601 234 567"]
    found = kinds(lines, "CV_Marta_Lewandowska.pdf")
    assert (KANDYDAT, "Marta Lewandowska") in found


def test_birth_date_in_words_and_family_status():
    # etykiety i wartości w osobnych kolumnach (typowe dla PDF z tabelą)
    lines = ["Data urodzenia:", "Stan cywilny:", "Wykształcenie:",
             "04 października 1982", "mężatka, dwoje dzieci syn (2008) i", "córka (2011)",
             "Praca z dziećmi w przedszkolu 2015-2018", "Opieka nad grupą dzieci w wieku 3-6 lat"]
    texts = {t for _, t in kinds(lines)}
    assert "04 października 1982" in texts
    assert "mężatka, dwoje dzieci syn (2008) i" in texts
    assert "córka (2011)" in texts
    # zwykłe doświadczenie zawodowe z dziećmi zostaje
    assert not any("przedszkolu" in t or "wieku" in t for t in texts)
    found = kinds(["Stan cywilny: żonaty", "ur. 3 maja 1990 r."])
    assert any(t == "żonaty" for _, t in found)
    assert any("1990" in t for _, t in found)


def test_personal_data_section_is_wiped():
    lines = ["CURRICULUM VITAE", "Dane osobowe", "Imię i nazwisko:", "Adres:", "Telefon:",
             "Narodowość:", "Anna Zielińska", "ul. Polna 5, 00-001 Warszawa,", "Polska",
             "600 700 800", "polska", "Doświadczenie zawodowe", "2015-2020 Księgowa, Firma XYZ"]
    found = detect(lines)
    texts = {f.text for f in found}
    for x in ["Anna Zielińska", "Polska", "600 700 800"]:
        assert x in texts, x
    # etykiety i treść po kolejnym nagłówku zostają
    assert not any(t in ("Telefon:", "Adres:") for t in texts)
    assert not any("Księgowa" in t or "Doświadczenie" in t for t in texts)
    # "Etykieta: wartość" w jednej linii
    texts2 = {f.text for f in detect(["DANE OSOBOWE", "Obywatelstwo: polskie", "Wiek: 42", "EDUKACJA", "Studia"])}
    assert {"polskie", "42"} <= texts2 and "Studia" not in texts2


def test_section_does_not_eat_experience():
    """Gdy nagłówek po sekcji ma nietypową nazwę, sekcja nie może zjeść doświadczenia."""
    lines = ["Dane osobowe", "Imię i nazwisko:", "Adres:", "Telefon:", "E-mail:", "Data urodzenia:",
             "Stan cywilny:", "Anna Zielińska", "ul. Polna 5, 00-001 Warszawa,", "Polska", "600 700 800",
             "anna@example.com", "04 października 1982", "mężatka, dwoje dzieci syn (2008) i", "córka (2011)",
             "Moja kariera filmowa", "Projekty niezależne | 07.2023–obecnie / freelance",
             "Kierowniczka produkcji / Producentka wykonawcza", "Talent Agent",
             "Przygotowywanie i obsługa umów cywilnoprawnych"]
    texts = {f.text for f in detect(lines)}
    for x in ["Anna Zielińska", "Polska", "04 października 1982", "córka (2011)"]:
        assert x in texts, x
    for x in ["Talent Agent", "Kierowniczka produkcji / Producentka wykonawcza",
              "Przygotowywanie i obsługa umów cywilnoprawnych", "Moja kariera filmowa"]:
        assert x not in texts, x


def test_law_date_in_consent_clause_is_kept():
    lines = ["Wyrażam zgodę na przetwarzanie danych osobowych zawartych w mojej ofercie pracy dla potrzeb niezbędnych",
             "do realizacji procesu rekrutacji zgodnie z ustawą z dnia 29 sierpnia 1997 r. o ochronie danych"]
    assert not any("1997" in f.text for f in detect(lines))


def test_reference_person_and_uppercase():
    lines = ["PIOTR WÓJCIK", "Referencje: Ewa Kamińska, tel. 600 100 200"]
    found = kinds(lines)
    assert (KANDYDAT, "PIOTR WÓJCIK") in found
    assert (OSOBA, "Ewa Kamińska") in found


# --- pliki ------------------------------------------------------------------

def _check(out: Path):
    text = "\n".join(engine.extract_lines(str(out)))
    for s in SECRETS:
        assert s.casefold() not in text.casefold(), f"zostało: {s}\n{text}"
    for s in KEEP:
        assert s in text, f"zniknęło: {s}"
    assert "[KANDYDAT]" in text
    return text


def test_docx(tmp_path):
    src = SAMPLES / "przykladowe_CV.docx"
    lines, findings = engine.analyze(str(src))
    out = tmp_path / "wynik.docx"
    st = engine.anonymize(str(src), str(out), findings)
    assert st["pozostalo"] == []
    assert st["zdjecia"] == 1
    _check(out)
    import zipfile
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert not any(n.startswith("word/media/") for n in names), "zdjęcie zostało w pliku"
        blob = b"".join(z.read(n) for n in names)
    assert b"wisniewska" not in blob.lower() and "Wiśniewska".encode() not in blob


def test_docx_blackout(tmp_path):
    src = SAMPLES / "przykladowe_CV.docx"
    _, findings = engine.analyze(str(src))
    out = tmp_path / "wynik.docx"
    engine.anonymize(str(src), str(out), findings, blackout=True, remove_photos=False)
    text = "\n".join(engine.extract_lines(str(out)))
    assert "█" in text and "Katarzyna" not in text


def test_txt(tmp_path):
    src = tmp_path / "cv.txt"
    src.write_text("Jan Kowalski\nE-mail: jan@example.com\nCV Jana Kowalskiego\n", encoding="cp1250")
    _, findings = engine.analyze(str(src))
    out = tmp_path / "out.txt"
    engine.anonymize(str(src), str(out), findings)
    t = out.read_text(encoding="cp1250")
    assert "Kowalsk" not in t and "jan@example.com" not in t


@pytest.mark.skipif(not HAS_PYMUPDF, reason="brak PyMuPDF")
def test_pdf(tmp_path):
    src = SAMPLES / "przykladowe_CV.pdf"
    lines, findings = engine.analyze(str(src))
    out = tmp_path / "wynik.pdf"
    st = engine.anonymize(str(src), str(out), findings)
    assert st["pozostalo"] == [], st
    assert st["zdjecia"] >= 1
    _check(out)
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    with fitz.open(out) as d:
        assert not d.metadata.get("author")
        assert not any(l.get("uri", "").startswith("mailto:") for p in d for l in p.get_links())
        assert len(d[0].get_image_info()) == 0


@pytest.mark.skipif(not HAS_PYMUPDF, reason="brak PyMuPDF")
def test_pdf_blackout(tmp_path):
    src = SAMPLES / "przykladowe_CV.pdf"
    _, findings = engine.analyze(str(src))
    out = tmp_path / "wynik.pdf"
    st = engine.anonymize(str(src), str(out), findings, blackout=True)
    assert st["pozostalo"] == []


def _ocr_ok():
    try:
        from anonimizator import ocr
        ocr.backend()
        return True
    except Exception:
        return False


HAS_OCR = _ocr_ok()


@pytest.mark.skipif(not HAS_OCR, reason="brak OCR")
def test_image_jpg(tmp_path):
    src = SAMPLES / "przykladowe_CV.jpg"
    lines, findings = engine.analyze(str(src))
    kinds_found = {f.kind for f in findings}
    assert {"E-mail", "Telefon", "Imię i nazwisko", "Adres"} <= kinds_found, kinds_found
    areas = engine.suggest_areas(str(src))
    assert len(areas) == 1, "zdjęcie powinno zostać wykryte"
    out = tmp_path / "wynik.jpg"
    st = engine.anonymize(str(src), str(out), findings, manual=areas)
    assert st["pozostalo"] == [], st
    assert st["zdjecia"] == 1
    text = "\n".join(engine.extract_lines(str(out)))
    for s_ in ["k.wisniewska", "602 345", "Kwiatowa", "Zieliński"]:
        assert s_ not in text, s_
    assert "Uniwersytet" in text
    from PIL import Image
    assert not Image.open(out).getexif(), "EXIF powinien być usunięty"


@pytest.mark.skipif(not HAS_OCR, reason="brak OCR")
def test_small_low_res_image(tmp_path):
    """Małe obrazki z internetu (ok. 470 px szerokości) - częsty przypadek."""
    from PIL import Image
    im = Image.open(SAMPLES / "przykladowe_CV.jpg")
    src = tmp_path / "maly.jpg"
    im.resize((466, round(im.height * 466 / im.width)), Image.LANCZOS).save(src, quality=80)
    _, findings = engine.analyze(str(src))
    kinds_found = {f.kind for f in findings}
    assert {"E-mail", "Telefon", "Imię i nazwisko"} <= kinds_found, kinds_found
    st = engine.anonymize(str(src), str(tmp_path / "out.jpg"), findings)
    assert st["pozostalo"] == [], st


@pytest.mark.skipif(not (HAS_OCR and HAS_PYMUPDF), reason="brak OCR lub PyMuPDF")
def test_scanned_pdf(tmp_path):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    scan = tmp_path / "skan.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=str(SAMPLES / "przykladowe_CV.jpg"))
    doc.save(scan)
    doc.close()
    assert engine.warnings_for(str(scan))
    assert len(engine.suggest_areas(str(scan))) == 1
    lines, findings = engine.analyze(str(scan))
    assert any(f.kind == "E-mail" for f in findings)
    out = tmp_path / "wynik.pdf"
    st = engine.anonymize(str(scan), str(out), findings)
    assert st["pozostalo"] == [], st
    text = "\n".join(engine.extract_lines(str(out)))
    assert "k.wisniewska" not in text and "Uniwersytet" in text


def test_unsupported(tmp_path):
    p = tmp_path / "cv.doc"
    p.write_bytes(b"x")
    with pytest.raises(engine.UnsupportedFile):
        engine.analyze(str(p))


def test_results_go_to_short_path():
    """Wyniki w krótkiej ścieżce - inaczej Reader/Excel na Windows ich nie otworzą (limit 260 znaków)."""
    d1 = engine.new_batch_dir()
    d2 = engine.new_batch_dir()
    try:
        assert d1 != d2 and d1.is_dir() and d2.is_dir()
        longest = d1 / ("CV_99.pdf")
        assert len(str(longest)) < 200
        assert len(str(d1 / "lista_kandydatow.csv")) < 200
    finally:
        d1.rmdir()
        d2.rmdir()


def test_output_name_has_no_personal_data():
    assert "Kowalski" not in engine.default_output_name("C:/CV_Jan_Kowalski.pdf")


@pytest.mark.skipif(importlib.util.find_spec("tkinter") is None, reason="brak tkinter")
def test_gui_smoke():
    import tkinter as tk
    try:
        from anonimizator.gui import App
        app = App(str(SAMPLES / "przykladowe_CV.docx"))
    except tk.TclError:
        pytest.skip("brak ekranu")
    result = {}

    def check():
        result["rows"] = len(app.tree.get_children())
        app.destroy()

    app.after(4000, check)
    app.mainloop()
    assert result["rows"] >= 8
