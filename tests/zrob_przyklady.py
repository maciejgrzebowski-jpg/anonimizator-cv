"""Generuje zmyślone przykładowe CV (DOCX i PDF) do testów. Uruchom: python tests/zrob_przyklady.py"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "przyklady"
OUT.mkdir(exist_ok=True)

HEADER = "Katarzyna Wiśniewska-Lis"
CONTACT = [
    "ul. Kwiatowa 15/3, 31-512 Kraków",
    "tel. +48 602 345 678",
    "e-mail: k.wisniewska.lis@example.com",
    "linkedin.com/in/katarzyna-wisniewska-lis",
    "Data urodzenia: 14.05.1991",
]
BODY = [
    ("Doświadczenie zawodowe", [
        "03.2020 – obecnie  Specjalistka ds. rekrutacji, Firma ABC Sp. z o.o., Kraków",
        "Prowadzenie procesów rekrutacyjnych, współpraca z kierownikami zespołów.",
        "09.2016 – 02.2020  Asystentka działu HR, XYZ S.A., Katowice",
    ]),
    ("Wykształcenie", [
        "2011 – 2016  Uniwersytet Jagielloński, psychologia (mgr)",
    ]),
    ("Umiejętności", [
        "MS Office, ATS (Teamtailor), język angielski C1, prawo jazdy kat. B",
    ]),
    ("Referencje", [
        "Tomasz Zieliński, kierownik HR, Firma ABC, tel. 501 222 333",
    ]),
    ("Klauzula", [
        "Wyrażam zgodę na przetwarzanie moich danych osobowych przez Katarzynę Wiśniewską-Lis "
        "w celu rekrutacji. Katarzyna Wiśniewska-Lis",
    ]),
]


def photo(path: Path):
    img = Image.new("RGB", (300, 380), (180, 200, 220))
    d = ImageDraw.Draw(img)
    d.ellipse((90, 60, 210, 190), fill=(240, 210, 180))
    d.rectangle((60, 220, 240, 380), fill=(60, 90, 140))
    img.save(path)


def make_docx(img: Path):
    from docx import Document
    from docx.shared import Cm, Pt
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()
    doc.core_properties.author = HEADER
    doc.sections[0].header.paragraphs[0].text = f"CV – {HEADER} – {CONTACT[2].split(': ')[1]}"
    t = doc.add_table(rows=1, cols=2)
    left, right = t.rows[0].cells
    left.paragraphs[0].add_run().add_picture(str(img), width=Cm(3))
    p = right.paragraphs[0]
    # imię i nazwisko rozbite na kilka fragmentów (tak bywa w prawdziwych plikach)
    for part in ("Katarzyna ", "Wiś", "niewska-Lis"):
        r = p.add_run(part)
        r.bold = True
        r.font.size = Pt(20)
    for c in CONTACT:
        if c.startswith("e-mail"):
            para = right.add_paragraph("e-mail: ")
            # klikalny link mailto:
            rid = para.part.relate_to("mailto:k.wisniewska.lis@example.com",
                                      "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                                      is_external=True)
            h = OxmlElement("w:hyperlink")
            h.set(qn("r:id"), rid)
            r = OxmlElement("w:r")
            tt = OxmlElement("w:t")
            tt.text = "k.wisniewska.lis@example.com"
            r.append(tt)
            h.append(r)
            para._p.append(h)
        else:
            right.add_paragraph(c)
    for title, items in BODY:
        doc.add_heading(title, level=2)
        for it in items:
            doc.add_paragraph(it)
    doc.save(OUT / "przykladowe_CV.docx")


def make_pdf(img: Path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("DV", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DVB", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    c = canvas.Canvas(str(OUT / "przykladowe_CV.pdf"), pagesize=A4)
    c.setAuthor(HEADER)
    c.setTitle(f"CV {HEADER}")
    w, h = A4
    c.setFillColorRGB(0.17, 0.27, 0.42)
    c.rect(0, h - 170, w, 170, fill=1, stroke=0)  # kolorowy nagłówek
    c.drawImage(str(img), 40, h - 155, width=105, height=133)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("DVB", 22)
    c.drawString(165, h - 60, HEADER)
    c.setFont("DV", 10)
    y = h - 82
    for line in CONTACT:
        c.drawString(165, y, line)
        y -= 15
    c.linkURL("mailto:k.wisniewska.lis@example.com", (165, h - 130, 420, h - 118))
    c.setFillColorRGB(0, 0, 0)
    y = h - 200
    for title, items in BODY:
        c.setFont("DVB", 12)
        c.drawString(40, y, title)
        y -= 18
        c.setFont("DV", 9.5)
        for it in items:
            while it:
                chunk = it[:95]
                if len(it) > 95:
                    chunk = chunk[:chunk.rfind(" ")]
                c.drawString(40, y, chunk)
                it = it[len(chunk):].lstrip()
                y -= 14
        y -= 10
    c.save()


if __name__ == "__main__":
    img = OUT / "_zdjecie.png"
    photo(img)
    make_docx(img)
    make_pdf(img)
    img.unlink()
    print("Gotowe:", OUT)
