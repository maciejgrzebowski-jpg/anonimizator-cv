"""Wykrywanie danych osobowych w tekście CV na podstawie reguł (bez AI)."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --- typy znalezisk i domyślne etykiety -------------------------------------
# Etykiety są bez polskich znaków, bo w PDF wstawiamy je standardową czcionką.
KANDYDAT = "Imię i nazwisko"
OSOBA = "Inna osoba"
EMAIL = "E-mail"
TELEFON = "Telefon"
PESEL = "PESEL / dokument"
ADRES = "Adres"
KOD = "Kod pocztowy / miasto"
LINK = "Profil / link"
URODZENIE = "Data / miejsce urodzenia"
WLASNE = "Dodane ręcznie"
PRYWATNE = "Stan cywilny / rodzina"
SEKCJA = "Sekcja: dane osobowe"

ETYKIETY = {
    KANDYDAT: "[KANDYDAT]",
    OSOBA: "[OSOBA]",
    EMAIL: "[E-MAIL]",
    TELEFON: "[TELEFON]",
    PESEL: "[PESEL]",
    ADRES: "[ADRES]",
    KOD: "[ADRES]",
    LINK: "[LINK]",
    URODZENIE: "[DATA URODZENIA]",
    WLASNE: "[USUNIETO]",
    PRYWATNE: "[USUNIETO]",
    SEKCJA: "[USUNIETO]",
}


@dataclass
class Finding:
    kind: str
    text: str
    replacement: str
    whole_word: bool = False  # True = dopasowuj tylko całe słowa (imiona, nazwiska)
    enabled: bool = True
    inflect: bool = False     # True = łap też formy odmienione (Kowalskiego, Annę...)

    @property
    def key(self) -> str:
        return " ".join(self.text.split()).casefold()


# --- słownik imion -----------------------------------------------------------

def _data_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)  # uruchomienie z PyInstallera
    if base:
        return Path(base) / "anonimizator" / "data"
    return Path(__file__).parent / "data"


def load_first_names() -> set[str]:
    names: set[str] = set()
    path = _data_dir() / "imiona.txt"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line.casefold())
    return names


FIRST_NAMES = load_first_names()

# Imiona, które często są zwykłymi słowami (np. "Jan" = styczeń po angielsku).
# Samo imię kandydata z tej listy nie będzie zamieniane wszędzie.
AMBIGUOUS_FIRST_NAMES = {"jan", "may", "will", "mark", "grace", "rose", "bill",
                         "roman", "lena", "nadia", "ada", "olga", "alex", "paul",
                         "lech", "maja"}

# Słowa pisane wielką literą, które nie są nazwiskami.
STOP_WORDS = {
    "curriculum", "vitae", "cv", "życiorys", "resume", "résumé", "profil", "profile",
    "doświadczenie", "zawodowe", "experience", "kontakt", "contact", "telefon", "tel",
    "phone", "e-mail", "email", "mail", "adres", "address", "umiejętności", "skills",
    "wykształcenie", "education", "o", "mnie", "about", "me", "języki", "languages",
    "zainteresowania", "hobby", "certyfikaty", "kursy", "szkolenia", "projekty",
    "sp", "z", "o.o", "s.a", "spółka", "ul", "al", "university", "uniwersytet",
    "politechnika", "akademia", "szkoła", "liceum", "technikum", "instytut",
    "street", "inżynier", "manager", "menedżer", "developer", "specjalista",
    "specjalistka", "kierownik", "kierowniczka", "dyrektor", "asystent", "asystentka",
    "senior", "junior", "mid", "lead", "analityk", "analityczka", "księgowa",
    "księgowy", "programista", "programistka", "tester", "testerka", "projektant",
    "projektantka", "sprzedawca", "konsultant", "konsultantka", "handlowiec",
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień",
    "wrzesień", "październik", "listopad", "grudzień", "january", "february",
    "march", "april", "june", "july", "august", "september", "october", "november",
    "december", "polska", "poland", "warszawa", "kraków", "wrocław", "poznań",
    "gdańsk", "łódź", "katowice", "lublin", "szczecin", "bydgoszcz", "białystok",
    "rzeszów", "toruń", "kielce", "olsztyn", "opole", "gdynia", "sopot", "the",
    "and", "of", "w", "i", "oraz", "na", "do", "dla", "im", "im.", "imienia",
    "excel", "word", "office", "microsoft", "google", "sap", "java", "python",
    "linkedin", "github", "prawo", "jazdy", "kat", "b", "data", "urodzenia",
    "miejsce", "imię", "nazwisko", "name", "obecnie", "present", "now",
    "edukacja", "kontakt", "dane", "osobowe", "kluczowe", "kompetencje", "podsumowanie",
    "osiągnięcia", "obowiązki", "referencje", "dodatkowe", "informacje", "obce", "social",
    "media", "kursy", "wybrane", "szkolenia", "zainteresowania", "certyfikaty", "summary",
    "personal", "information", "interests", "career", "objective", "cel", "zawodowy",
    "portfolio", "praktyki", "staż", "wolontariat", "sprzedawca", "sprzedawczyni",
    "nauczyciel", "nauczycielka", "księgowa", "marketingu", "marketing", "ds", "ds.",
    "specjalista", "kierowniczka", "absolwent", "absolwentka", "student", "studentka",
}

# --- wyrażenia regularne -----------------------------------------------------
UP = "A-ZĄĆĘŁŃÓŚŹŻÄÖÜÉÈ"
LO = "a-ząćęłńóśźżäöüéèß"
NAME_TOKEN = re.compile(rf"[{UP}][{LO}{UP}'’]+(?:-[{UP}][{LO}{UP}'’]+)?")

RE_EMAIL = re.compile(r"[\w.+-]+ ?@ ?[\w-]+(?:\.[\w-]+)+")  # spacje: częsty błąd OCR
RE_PHONE = re.compile(
    r"(?<![\d+\w])"
    r"(?:(?:\+|00)\s?\d{2}[\s.-]?|\(\+?\d{2}\)\s?)?"
    r"(?:\d{3}[\s.-]?\d{3}[\s.-]?\d{3}|\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2})"
    r"(?!\d)"
)
RE_PHONE_INTL = re.compile(r"(?<![\d\w])\+\d{1,3}(?:[\s.-]?\(?\d{1,5}\)?){2,5}(?!\d)")
# OCR potrafi zgubić kropkę lub zamienić znak - każde "słowo" z @ traktujemy jak e-mail
RE_EMAIL_LOOSE = re.compile(r"[\w.+-]*\w ?@ ?\w[\w.-]*(?: ?\. ?(?:com|pl|eu|net|org|info|de|uk))?")
# e-mail z typowymi błędami OCR: ® © zamiast @, zgubiona kropka, "emal", "gmai"...
RE_EMAIL_OCR = re.compile(
    r"(?i)(?<![\w@®©])[\w.+-]{2,}[®©][\w.-]{2,}(?: ?\.? ?(?:com|pl|eu|net|org))?"
    r"|(?<![\w])(?:[\w.+-]{2,} )?[\w.+-]*(?:e-?ma[il1|]{0,2}|g? ?ma[il1|]{1,2}|hotma[il1|]{1,2}|outlook|interia|onet|icloud|wp)"
    r"[\w,-]*(?: ?[.,] ?| )(?:com|pl|eu|net)(?![\w])"
    r"|(?<![\w])[a-z][\w.]{6,}com(?![\w])"
)
# długie "słowo" + "pl"/"com" na końcu linii - e-mail lub strona, z której OCR zgubił @ i kropkę
RE_EMAIL_TAIL = re.compile(r"(?<![\w])[a-z][\w.]{9,}\s?[.,]?\s?(?:pl|com|eu)\s*$")
# telefon z literami pomylonymi z cyframi (O=0, I/l/|=1, Z=2, S=5, B=8, T=7)
RE_PHONE_OCR = re.compile(r"(?<![\w])[\dOoIl|ZSBT\[\]!](?:[ ./-]?[\dOoIl|ZSBT\[\]!]){8,13}(?![\w])")
OCR_DIGITS = str.maketrans("OoIl|ZSBT[]!", "001112587111")
# etykieta w osobnej linii, a wartość w następnej (częste w CV z kolumnami)
LABEL_ONLY = [
    (re.compile(r"(?i)^\s*(?:tel\.?|telefon|phone|mobile|komórka|nr\s+tel\.?)\s*:?\s*$"), TELEFON),
    (re.compile(r"(?i)^\s*(?:e-?mail|mail|adres\s+e-?mail)\s*:?\s*$"), EMAIL),
    (re.compile(r"(?i)^\s*(?:adres|address|adres\s+zamieszkania)\s*:?\s*$"), ADRES),
    (re.compile(r"(?i)^\s*(?:da\w{1,3}\s+ur\.?|data\s+urodzenia|date\s+of\s+birth|urodzon[ya])\s*:?\s*$"), URODZENIE),
    (re.compile(r"(?i)^\s*(?:linked\s?in|github|facebook|instagram|www)\s*:?[\W_]*$"), LINK),
]

# pełna data z rokiem 1940-2009 = najpewniej data urodzenia (daty pracy to zwykle mm.rrrr)
RE_BIRTH_LIKE = re.compile(r"(?<![\d.])(?:0?[1-9]|[12]\d|3[01]) ?[./-]? ?(?:0?[1-9]|1[0-2]) ?[./-] ?(?:19[4-9]\d|200\d)(?!\d)")
# data zapisana słownie: "04 października 1982", "4 Oct 1982"
MONTHS = (r"stycz\w*|lut\w*|mar(?:ca|zec)|kwie\w*|maj\w*|czerw\w*|lip\w*|sierp\w*|wrze\w*|"
          r"pa[źz]dzier\w*|listopad\w*|grud\w*|jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|"
          r"sep\w*|oct\w*|nov\w*|dec\w*")
RE_BIRTH_WORDS = re.compile(rf"(?i)(?<!\w)(?:0?[1-9]|[12]\d|3[01])\.?\s+(?:{MONTHS})\s+(?:19[4-9]\d|200\d)(?:\s?r\.)?(?!\d)")
# stan cywilny i dzieci - nie powinny wpływać na ocenę kandydata
RE_FAMILY = re.compile(
    r"(?i)(?<!\w)(?:mężatka|zamężna|żonaty|kawaler|panna|rozwiedzion\w*|rozwódka|rozwodnik|wdowa|wdowiec|"
    r"w\s+związku\s+małżeńskim|married|single|divorced|widow\w*)(?!\w)"
    r"|(?<!\w)(?:jedno|dwoje|troje|czworo|\d+)\s+dzieci(?!\w)"
    r"|(?<!\w)(?:syn|córka|córki|synowie|synów|dzieci|dziecko|son|daughter|children)\s*\(?\s*(?:19|20)\d\d"
)
FAMILY_LABEL = re.compile(r"(?i)\b(?:stan\s+cywilny|marital\s+status|dzieci|children|wyznanie|religia)\s*[:–—-]\s*")

# sekcja CV, której całą zawartość usuwamy
SECTION_PERSONAL = re.compile(
    r"(?i)^\W*(?:dane\s+osobowe|dane\s+personalne|informacje\s+osobiste|dane\s+kontaktowe|kontakt|"
    r"personal\s+(?:data|details|information|info)|contact(?:\s+details|\s+information)?)\W*$")
SECTION_HEADINGS = re.compile(
    r"(?i)^\W*(?:doświadczenie(?:\s+zawodowe)?|przebieg\s+(?:pracy|kariery|zatrudnienia)|wykształcenie|edukacja|"
    r"umiejętności|kompetencje|kluczowe\s+kompetencje|języki(?:\s+obce)?|znajomość\s+języków|kursy|szkolenia|"
    r"kursy\s+i\s+szkolenia|certyfikaty|zainteresowania|hobby|podsumowanie|profil(?:\s+zawodowy)?|o\s+mnie|"
    r"cel\s+zawodowy|osiągnięcia|referencje|dodatkowe\s+informacje|informacje\s+dodatkowe|uprawnienia|"
    r"wybrane\s+szkolenia|social\s+media|experience|work\s+experience|education|skills|languages|"
    r"courses|certificates|interests|summary|profile|about\s+me|references)\W*$")
SECTION_MAX_LINES = 15
SECTION_MAX_LEN = 60
# okres zatrudnienia / nauki - znak, że to już nie są dane osobowe
RE_DATE_RANGE = re.compile(r"(?i)(?:\d{2}[./]\d{4}|\b(?:19|20)\d\d)\s*[–—-]\s*(?:\d{2}[./]\d{4}|(?:19|20)\d\d|obecnie|nadal|present|now)")

# linia "kontaktowa" - tu OCR najczęściej przekręca e-mail i linki
RE_CONTACTISH = re.compile(r"(?i)com|con\b|\bpl\b|\.pl|@|®|©|mail|www|http|linked|lnkd")

# 9-12 cyfr w ciągu (np. telefon odczytany przez OCR bez spacji lub z błędem)
RE_DIGITS = re.compile(r"(?<![\d.,/-])\d{9,12}(?!\d)(?![.,/-]\d)")
RE_PESEL = re.compile(r"(?<!\d)\d{11}(?!\d)")
RE_POSTAL = re.compile(
    rf"(?<![\d-])\d{{2}}-\d{{3}}(?![\d-])"
    rf"(?:\s+[{UP}][{LO}]+(?:[\s-][{UP}][{LO}]+)?)?"
)
RE_STREET = re.compile(
    rf"(?<!\w)(?:[Uu]l\.|[Uu]lica|[Aa]l\.|[Aa]leja|[Aa]leje|[Oo]s\.|[Oo]siedle|[Pp]l\.|[Pp]lac)"
    rf"\s*[{UP}0-9][\w.'’ -]{{1,40}}?\s\d+[a-zA-Z]?"
    rf"(?:\s?/\s?\d+[a-zA-Z]?|\s?(?:m\.|lok\.|m)\s?\d+)?"
)
RE_URL = re.compile(
    r"(?i)(?<![\w.])(?:https?://)?(?:[a-z]{2,3}\.)?(?:www\.)?"
    r"(?:linkedin\.com|github\.com|gitlab\.com|facebook\.com|fb\.com|instagram\.com|"
    r"twitter\.com|x\.com|behance\.net|dribbble\.com|goldenline\.pl|tiktok\.com|youtube\.com)"
    r" ?/ ?[^\s,;)\]]+"
)
DATE = r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[^\W\d_]+\s+\d{4})"
RE_BIRTH_DATE = re.compile(rf"(?i)(?<!\w)(?:ur\.|urodzon[ya]|born)\s*:?\s*({DATE})")

# Pola z etykietą: "Adres: ...", "Data urodzenia: ..." itd. -> bierzemy resztę linii
LABELLED = [
    (re.compile(r"(?i)\b(?:adres(?:\s+zamieszkania|\s+do\s+korespondencji)?|address|home address)\s*[:–—-]\s*"), ADRES),
    (re.compile(r"(?i)\b(?:data\s+(?:i\s+miejsce\s+)?urodzenia|data\s+ur\.|date\s+of\s+birth|date\s+and\s+place\s+of\s+birth|dob|miejsce\s+urodzenia|place\s+of\s+birth)\s*[:–—-]\s*"), URODZENIE),
    (re.compile(r"(?i)\b(?:pesel|nr\s+dowodu(?:\s+osobistego)?|seria\s+i\s+numer\s+dowodu|nr\s+paszportu)\s*[:–—-]\s*"), PESEL),
    (re.compile(r"(?i)\b(?:imię\s+i\s+nazwisko|imie\s+i\s+nazwisko|full\s+name|nazwisko|imię|imiona)\s*[:–—-]\s*"), KANDYDAT),
]


def pesel_ok(s: str) -> bool:
    w = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    d = [int(c) for c in s]
    return (10 - sum(a * b for a, b in zip(w, d)) % 10) % 10 == d[10]


def _clean(s: str) -> str:
    return " ".join(s.split()).strip(" ,;|•·")


# --- wykrywanie imienia i nazwiska ------------------------------------------

def _tokens(line: str):
    return [(m.group(), m.start(), m.end()) for m in NAME_TOKEN.finditer(line)]


def _is_surname(tok: str) -> bool:
    low = tok.casefold()
    return low not in STOP_WORDS and len(tok) >= 2 and not tok.isdigit()


def _name_from_line(line: str) -> str | None:
    """Szuka w linii pary imię + nazwisko (lub nazwisko + imię)."""
    toks = _tokens(line)
    for i, (tok, s, e) in enumerate(toks):
        if tok.casefold() not in FIRST_NAMES:
            continue
        # imię (+ drugie imię) + nazwisko
        j = i + 1
        while j < len(toks) and toks[j][0].casefold() in FIRST_NAMES and j + 1 < len(toks) \
                and _adjacent(line, toks[j - 1], toks[j]):
            j += 1
        if j < len(toks) and _adjacent(line, toks[j - 1], toks[j]) and _is_surname(toks[j][0]):
            return line[s:toks[j][2]]
        # nazwisko + imię ("Kowalski Jan")
        if i > 0 and _adjacent(line, toks[i - 1], toks[i]) and _is_surname(toks[i - 1][0]) \
                and toks[i - 1][0].casefold() not in FIRST_NAMES:
            return line[toks[i - 1][1]:e]
    return None


def _adjacent(line: str, a, b) -> bool:
    return line[a[2]:b[1]].strip() == ""


def _looks_like_bare_name(line: str) -> str | None:
    """Linia złożona wyłącznie z 2-3 słów pisanych wielką literą (np. nagłówek CV)."""
    s = line.strip()
    if not s or any(ch.isdigit() for ch in s) or len(s) > 50:
        return None
    toks = _tokens(s)
    joined = " ".join(t[0] for t in toks)
    if 2 <= len(toks) <= 3 and _clean(joined) == _clean(s) \
            and all(t[0].casefold() not in STOP_WORDS for t in toks):
        return s
    return None


def _name_tokens_ok(text: str) -> bool:
    toks = text.split()
    if not 1 <= len(toks) <= 4 or any(ch.isdigit() for ch in text):
        return False
    for t in toks:
        core = t.strip(".,;:|")
        if len(core) < 2 or not all(ch.isalpha() or ch in "-'’" for ch in core):
            return False
        if not core[0].isupper() or core.casefold() in STOP_WORDS:
            return False
    return True


def _name_from_titles(titles) -> str | None:
    """Największy napis na stronie wyglądający jak imię i nazwisko."""
    if not titles:
        return None
    big = [t for t in titles[:6] if t[2].strip()]
    if not big:
        return None
    top_h = big[0][0]
    for h, y, text in big[:3]:
        if h < 0.6 * top_h:
            break
        text = _clean(text)
        if _name_tokens_ok(text) and len(text.split()) >= 2:
            return text
        # imię i nazwisko w dwóch liniach tej samej wielkości (np. "Katarzyna" / "Kowalska")
        if _name_tokens_ok(text) and len(text.split()) == 1:
            for h2, y2, t2 in big:
                t2 = _clean(t2)
                if t2 != text and abs(h2 - h) <= 0.2 * h and _name_tokens_ok(t2) and len(t2.split()) == 1 \
                        and abs(y2 - y) <= 2.5 * h:
                    return f"{text} {t2}" if y <= y2 else f"{t2} {text}"
    return None


def find_candidate_name(lines: list[str], filename: str | None = None, titles=None) -> str | None:
    top = [l for l in lines if l.strip()][:15]
    # 1) pole "Imię i nazwisko: ..."
    for l in lines:
        for rx, kind in LABELLED:
            if kind == KANDYDAT:
                m = rx.search(l)
                if m and _clean(l[m.end():]):
                    return _clean(l[m.end():])
    # 2) największy napis na stronie (obrazki, PDF)
    n = _name_from_titles(titles)
    if n:
        return n
    # 3) imię ze słownika + nazwisko w górnej części CV
    for l in top:
        n = _name_from_line(l)
        if n:
            return _clean(n)
    # 3) nazwa pliku, np. "CV_Jan_Kowalski.pdf"
    if filename:
        stem = re.sub(r"[_.\-]+", " ", Path(filename).stem)
        n = _name_from_line(" ".join(w.capitalize() if w.islower() else w for w in stem.split()))
        if n:
            # odszukaj tę samą parę w tekście (zachowując zapis z dokumentu)
            for l in lines:
                if all(p.casefold() in l.casefold() for p in n.split()):
                    return _clean(n)
            return _clean(n)
    # 4) pierwsza linia wyglądająca jak samo imię i nazwisko
    for l in top[:5]:
        n = _looks_like_bare_name(l)
        if n:
            return _clean(n)
    return None


# --- główna funkcja ----------------------------------------------------------

def _label_value_ok(kind: str, val: str) -> bool:
    """Czy wartość z linii pod etykietą pasuje do rodzaju danych (chroni przed pomyłką kolumn)."""
    if kind == TELEFON:
        return len(re.sub(r"\D", "", val.translate(OCR_DIGITS))) >= 7 and len(val) <= 25
    if kind == EMAIL:
        return bool(re.search(r"(?i)@|®|©|mail|\.com|\.pl|\bcom\b|\bpl\b", val)) and len(val.split()) <= 4
    if kind == URODZENIE:
        return bool(re.search(r"(?:19|20)\d\d|\d{1,2}[./ ]\d{1,2}", val)) and len(val) <= 30
    if kind == LINK:
        return bool(re.search(r"[./]", val)) and len(val.split()) <= 4
    if kind == ADRES:
        return len(val) <= 50 and len(val.split()) <= 6
    return True


def detect(lines: list[str], filename: str | None = None, titles=None,
           candidate: str | None = None) -> list[Finding]:
    found: dict[str, Finding] = {}

    def add(kind: str, text: str, whole_word: bool = False):
        text = _clean(text)
        if len(text) < 2:
            return
        f = Finding(kind, text, ETYKIETY[kind], whole_word, inflect=kind in (KANDYDAT, OSOBA))
        if f.key not in found:
            found[f.key] = f

    # kandydat
    cand = candidate or find_candidate_name(lines, filename, titles)
    if cand:
        add(KANDYDAT, cand, True)
        parts = [p for p in cand.split() if len(p) >= 2]
        if len(parts) == 2:
            add(KANDYDAT, " ".join(reversed(parts)), True)
        for p in parts:
            low = p.casefold()
            if low in FIRST_NAMES and low in AMBIGUOUS_FIRST_NAMES:
                continue
            add(KANDYDAT, p, True)

    for l in lines:
        for m in RE_EMAIL.finditer(l):
            add(EMAIL, m.group())
        if "@" in l and not RE_EMAIL.search(l):
            for m in RE_EMAIL_LOOSE.finditer(l):
                add(EMAIL, m.group())
        if not RE_EMAIL.search(l):
            for m in list(RE_EMAIL_OCR.finditer(l)) + list(RE_EMAIL_TAIL.finditer(l)):
                v = m.group()
                if not RE_URL.search(v) and not re.match(
                        r"(?i)(?:https?|www|linked\s?in|github|facebook|instagram|twitter)", v):
                    add(EMAIL, v)
        for m in RE_URL.finditer(l):
            add(LINK, m.group().rstrip("."))
        no_mail = RE_URL.sub(" ", RE_EMAIL.sub(" ", l))
        for m in RE_PESEL.finditer(no_mail):
            if pesel_ok(m.group()):
                add(PESEL, m.group())
        for m in RE_PHONE.finditer(no_mail):
            add(TELEFON, m.group())
        for m in RE_DIGITS.finditer(no_mail):
            if not (len(m.group()) == 11 and pesel_ok(m.group())):
                add(TELEFON, m.group())
        for m in RE_PHONE_OCR.finditer(no_mail):
            raw = m.group().strip()
            digits = re.sub(r"\D", "", raw.translate(OCR_DIGITS))
            real = sum(ch.isdigit() for ch in raw)
            if 9 <= len(digits) <= 12 and real >= 6 and any(ch in "OoIl|ZSBT[]!" for ch in raw):
                add(TELEFON, raw)
        for m in RE_PHONE_INTL.finditer(no_mail):
            digits = re.sub(r"\D", "", m.group())
            if 9 <= len(digits) <= 15:
                add(TELEFON, m.group())
        for m in RE_STREET.finditer(l):
            add(ADRES, m.group())
        for m in RE_POSTAL.finditer(l):
            add(KOD, m.group())
            # tekst przed kodem pocztowym z numerem domu = ulica (nawet gdy OCR przekręcił "ul.")
            before = re.sub(r"^[^A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", "", l[:m.start()]).strip(" ,;|")
            if before and len(before) <= 50 and re.search(r"\d", before):
                add(ADRES, before)
        birth_ctx = len(l.strip()) <= 40 or re.search(r"(?i)urodz|\bur\.|born|birth", l)
        if birth_ctx:
            for m in RE_BIRTH_WORDS.finditer(l):
                add(URODZENIE, m.group())
        # stan cywilny / dzieci: cała (krótka) linia z taką informacją
        fl = FAMILY_LABEL.search(l)
        if fl and _clean(l[fl.end():]):
            add(PRYWATNE, l[fl.end():])
        elif RE_FAMILY.search(l) and len(l.strip()) <= 90:
            add(PRYWATNE, l)
        if birth_ctx:
            for m in RE_BIRTH_LIKE.finditer(l):
                add(URODZENIE, m.group())
        for m in RE_BIRTH_DATE.finditer(l):
            add(URODZENIE, m.group(1))
        for rx, kind in LABELLED:
            if kind == KANDYDAT:
                continue
            m = rx.search(l)
            if m:
                val = _clean(l[m.end():])
                if val and len(val) <= 120:
                    add(kind, val)

    # nazwisko kandydata przekręcone przez OCR w e-mailu / linku (np. "lamczy<jŻg com")
    if cand:
        surnames = [p for p in cand.split() if len(p) >= 5 and p.casefold() not in FIRST_NAMES]
        for l in lines:
            if not RE_CONTACTISH.search(l):
                continue
            toks = l.split()
            for i, tok in enumerate(toks):
                letters = "".join(ch for ch in tok.casefold() if ch.isalpha())
                if any(_fuzzy_contains(letters, sn.casefold()) for sn in surnames):
                    val = tok
                    if i + 1 < len(toks) and re.fullmatch(r"(?i)[.,]?(?:com|con|pl|eu|net)\W*", toks[i + 1]):
                        val += " " + toks[i + 1]
                    add(EMAIL if RE_EMAIL_OCR.search(l) or "@" in l or "mail" in l.lower() or re.search(r"(?i)com|pl", val)
                        else LINK, val)

    # sekcja "Dane osobowe" / "Kontakt": tyle wartości, ile etykiet (+ zapas na dopiski)
    nonempty_all = [l for l in lines if l.strip()]
    for i, head in enumerate(nonempty_all):
        if not SECTION_PERSONAL.match(head):
            continue
        window = []
        for l in nonempty_all[i + 1:i + 1 + SECTION_MAX_LINES]:
            line = _clean(l)
            if SECTION_HEADINGS.match(l) or SECTION_PERSONAL.match(l) or len(line) > SECTION_MAX_LEN \
                    or RE_DATE_RANGE.search(line):
                break  # koniec sekcji: nagłówek, długi opis albo okres pracy
            if line:
                window.append(line)
        label_only = [x for x in window if re.fullmatch(r"[^:]{2,30}:", x)]
        budget = len(label_only) + 2 if label_only else 0
        for line in window:
            m = re.match(r"^([^:]{2,30}):\s*(.*)$", line)
            if m:  # "Etykieta: wartość" -> zostaw etykietę
                if _clean(m.group(2)):
                    add(SEKCJA, m.group(2))
                continue
            if budget > 0:
                add(SEKCJA, line)
                budget -= 1
            elif not label_only and re.search(r"\d|@|www|ul\.", line):
                add(SEKCJA, line)  # sekcja bez etykiet: tylko linie wyglądające na kontakt

    # etykieta w jednej linii, wartość w następnej
    nonempty = [l for l in lines if l.strip()]
    for i, l in enumerate(nonempty[:-1]):
        for rx, kind in LABEL_ONLY:
            if rx.match(l):
                val = _clean(nonempty[i + 1])
                if val and _label_value_ok(kind, val) and not any(r.match(val) for r, _ in LABEL_ONLY):
                    add(kind, val)

    # inne osoby (np. referencje): imię ze słownika + nazwisko
    cand_keys = {k for k, f in found.items() if f.kind == KANDYDAT}
    for l in lines:
        toks = _tokens(l)
        for i in range(len(toks) - 1):
            a, b = toks[i], toks[i + 1]
            if a[0].casefold() in FIRST_NAMES and _adjacent(l, a, b) and _is_surname(b[0]) \
                    and b[0].casefold() not in FIRST_NAMES:
                pair = l[a[1]:b[2]]
                key = " ".join(pair.split()).casefold()
                if key in cand_keys or any(key in k or k in key for k in cand_keys):
                    continue
                add(OSOBA, pair, True)

    # kolejność: od najdłuższych (ważne przy zamianie)
    return sorted(found.values(), key=lambda f: (-len(f.text), f.kind))


def _lev(a: str, b: str, limit: int) -> int:
    """Odległość edycyjna (z odcięciem) - do porównań z błędami OCR."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _fuzzy_contains(text: str, name: str) -> bool:
    """Czy w tekście jest (z dokładnością do 1-2 błędów OCR) dane nazwisko."""
    stem = name[:-1] if name[-1] in VOWELS else name  # Kowalska -> Kowalsk (też Kowalski)
    limit = 1 if len(stem) < 7 else 2
    n = len(stem)
    for size in (n - 1, n, n + 1):
        for i in range(0, max(1, len(text) - size + 1)):
            if _lev(text[i:i + size], stem, limit) <= limit:
                return True
    return False


def add_custom(findings: list[Finding], text: str, replacement: str | None = None) -> Finding | None:
    text = _clean(text)
    if not text:
        return None
    f = Finding(WLASNE, text, replacement or ETYKIETY[WLASNE], whole_word=False)
    if any(x.key == f.key for x in findings):
        return None
    findings.append(f)
    findings.sort(key=lambda x: -len(x.text))
    return f


# Końcówki odmiany polskich imion i nazwisk (od najdłuższych).
SUFFIXES = sorted({"", "a", "y", "i", "e", "ie", "ę", "ą", "o", "u", "owi", "em", "om",
                   "ego", "emu", "iem", "im", "ym", "ej", "iej", "iego", "iemu", "ich", "ach", "ami"},
                  key=len, reverse=True)
VOWELS = "aeiouyąęó"


# litery z polskimi znakami i bez - OCR i ludzie często je gubią (Wiśniewska = Wisniewska)
_FOLD = {"a": "aą", "c": "cć", "e": "eę", "l": "lł", "n": "nń", "o": "oó", "s": "sś", "z": "zźż"}
for _base, _all in list(_FOLD.items()):
    for _ch in _all[1:]:
        _FOLD[_ch] = _all


def _fold(text: str) -> str:
    """Wzorzec tekstu, w którym litera z ogonkiem pasuje też do litery bez ogonka."""
    out = []
    for ch in text:
        low = ch.lower()
        if low in _FOLD:
            out.append("[" + _FOLD[low] + _FOLD[low].upper() + "]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def _inflected(word: str) -> str:
    """Wzorzec słowa z dowolną typową końcówką odmiany."""
    if len(word) < 3:
        return _fold(word)
    stems = {word[:-1] if word[-1].lower() in VOWELS else word}
    if word.lower().endswith("ek") and len(word) > 4:  # Marek -> Marka
        stems.add(word[:-2] + word[-1])
    suf = "|".join(re.escape(x) for x in SUFFIXES)
    return "(?:" + "|".join(_fold(st) for st in sorted(stems, key=len, reverse=True)) + f")(?:{suf})"


def token_pattern(token: str, inflect: bool) -> str:
    if not inflect:
        return _fold(token)
    return "-".join(_inflected(p) for p in token.split("-"))


def build_pattern(f: Finding) -> re.Pattern:
    """Wzorzec wyszukiwania dla znaleziska (elastyczne białe znaki, bez wielkości liter)."""
    parts = [token_pattern(p, f.inflect) for p in f.text.split()]
    body = r"\s+".join(parts)
    if f.whole_word:
        body = rf"(?<!\w){body}(?!\w)"
    return re.compile(body, re.IGNORECASE)
