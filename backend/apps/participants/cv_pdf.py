"""Draws the CV document (from :mod:`cv`) as an A4 PDF with reportlab.

Only the document passed in is drawn, so whatever :func:`cv.build` leaves out never reaches the
file. Sections with nothing in them are skipped. Headings stay with the entry that follows them
and an entry is not split across pages where it fits on one."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
ACCENT = colors.HexColor("#0f4c81")
RULE = colors.HexColor("#d1d5db")
MARGIN = 18 * mm
WIDTH = A4[0] - 2 * MARGIN


def _style(name, **kw):
    base = {
        "fontName": "Helvetica",
        "fontSize": 9.5,
        "leading": 13,
        "textColor": INK,
        "alignment": TA_LEFT,
    }
    return ParagraphStyle(name, **{**base, **kw})


NAME = _style("name", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=ACCENT)
HEADLINE = _style("headline", fontSize=11, leading=14, textColor=MUTED)
CONTACT = _style("contact", fontSize=9, leading=13, textColor=INK)
H2 = _style(
    "h2",
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=ACCENT,
    spaceBefore=12,
    spaceAfter=2,
    keepWithNext=1,
)
BODY = _style("body")
ENTRY = _style("entry", fontName="Helvetica-Bold", fontSize=10, leading=13)
SUB = _style("sub", textColor=MUTED)
BULLET = _style("bullet", leftIndent=10, bulletIndent=0, spaceBefore=1)
WHEN = _style("when", textColor=MUTED, alignment=2, fontSize=9)  # right aligned


def _p(text, style=BODY):
    """A paragraph of user text: escaped, with line breaks kept."""
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def _heading(title):
    return [
        Paragraph(escape(title.upper()), H2),
        HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=5),
    ]


def _entry(title, when, lines, bullets=()):
    """One dated entry: a title row, grey sub lines, then optional text. Kept on one page."""
    head = Table(
        [[_p(title, ENTRY), _p(when, WHEN)]],
        colWidths=[WIDTH * 0.72, WIDTH * 0.28],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )
    parts = [head]
    for line in lines:
        if line:
            parts.append(_p(line, SUB))
    for text in bullets:
        if text:
            parts.append(Paragraph(escape(text).replace("\n", "<br/>"), BULLET, bulletText="•"))
    parts.append(Spacer(1, 6))
    return KeepTogether(parts)


def _bulleted(text):
    """Split free text into lines; each non empty line becomes a bullet."""
    return [x.strip(" -•\t") for x in (text or "").splitlines() if x.strip(" -•\t")]


def _photo(data):
    """The photo scaled into a 30mm square, or None if it cannot be drawn."""
    if not data:
        return None
    try:
        img = Image(BytesIO(data), width=30 * mm, height=30 * mm)
        ImageReader(BytesIO(data))  # fails early on a broken image
        return img
    except Exception:  # noqa: BLE001 - a bad photo must never stop the CV downloading
        return None


def _header(cv, photo):
    c = cv["contact"]
    left = [Paragraph(escape(cv["name"]), NAME)]
    if cv["headline"]:
        left.append(Paragraph(escape(cv["headline"]), HEADLINE))
    left.append(Spacer(1, 4))
    for label, value in (("Phone", c["phone"]), ("Email", c["email"]), ("Location", c["location"])):
        if value:
            left.append(
                Paragraph(f'<font color="#6b7280">{label}:</font> {escape(value)}', CONTACT)
            )
    pic = _photo(photo)
    if pic is None:
        return left
    table = Table(
        [[left, pic]],
        colWidths=[WIDTH - 34 * mm, 34 * mm],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )
    return [table]


class _Numbered(canvas.Canvas):
    """Adds 'Page x of y' and the name to every page once the page count is known."""

    name = ""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._saved = []

    def showPage(self):  # noqa: N802 - reportlab API
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 8)
            self.setFillColor(MUTED)
            self.drawString(MARGIN, 10 * mm, f"{self.name} - Curriculum Vitae")
            self.drawRightString(A4[0] - MARGIN, 10 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def render(cv: dict, photo: bytes | None = None) -> bytes:
    story = _header(cv, photo)
    story.append(Spacer(1, 4))

    if cv["summary"]:
        story += _heading("Professional summary") + [_p(cv["summary"])]

    if cv["experience"] or cv["no_work_experience"]:
        story += _heading("Work experience")
        if not cv["experience"]:
            story.append(_p("No formal work experience yet.", SUB))
        for e in cv["experience"]:
            sub = " | ".join(x for x in (e["employer"], e["employment_type"]) if x)
            when = " | ".join(x for x in (e["period"], e["duration"]) if x)
            bullets = _bulleted(e["responsibilities"])
            if e["achievements"]:
                bullets += ["Achievement: " + x for x in _bulleted(e["achievements"])]
            story.append(_entry(e["title"], when, [sub], bullets))

    if cv["practical"]:
        story += _heading("Internships and practical experience")
        for x in cv["practical"]:
            title = x["role"] or x["kind"]
            sub = " | ".join(y for y in (x["organisation"], x["kind"] if x["role"] else "") if y)
            story.append(_entry(title, x["period"], [sub], _bulleted(x["description"])))

    if cv["education"]:
        story += _heading("Education")
        for q in cv["education"]:
            title = q["course"] or q["level"]
            sub = " | ".join(y for y in (q["institution"], q["level"] if q["course"] else "") if y)
            more = " | ".join(
                y
                for y in (q["field_of_study"], ("Grade: " + q["grade"]) if q["grade"] else "")
                if y
            )
            story.append(_entry(title, q["period"], [sub, more]))

    if cv["skills"]:
        story += _heading("Skills")
        story.append(_p("  |  ".join(s["name"] for s in cv["skills"])))

    if cv["certifications"]:
        story += _heading("Certifications and training")
        for c in cv["certifications"]:
            when = str(c["year"]) if c["year"] else ""
            sub = " | ".join(
                y for y in (c["issuer"], ("Expires " + c["expiry"]) if c["expiry"] else "") if y
            )
            story.append(_entry(c["name"], when, [sub]))

    if cv["languages"]:
        story += _heading("Languages")
        story.append(
            _p(
                "  |  ".join(
                    f"{x['language']} ({x['level']})" if x["level"] else x["language"]
                    for x in cv["languages"]
                )
            )
        )

    pref = cv["preferences"]
    if pref:
        story += _heading("Employment preferences")
        rows = [
            ("Preferred roles", ", ".join(pref["roles"])),
            ("Sectors", ", ".join(pref["sectors"])),
            ("Preferred locations", ", ".join(pref["counties"])),
            ("Work pattern", ", ".join(pref["work_patterns"])),
            ("Available from", pref["available_from"]),
            (
                "Willing to relocate",
                {True: "Yes", False: "No"}.get(pref["willing_to_relocate"], ""),
            ),
        ]
        for label, value in rows:
            if value:
                story.append(
                    Paragraph(
                        f'<font color="#6b7280">{escape(label)}:</font> {escape(value)}', BODY
                    )
                )

    buf = BytesIO()
    numbered = type("_NumberedCv", (_Numbered,), {"name": cv["name"]})  # one per call
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=18 * mm,
        title=f"{cv['name']} - CV",
        author=cv["name"],
        subject="Curriculum Vitae",
    )
    # No frame padding, so tables and paragraphs share the same left and right edge.
    frame = Frame(
        MARGIN,
        18 * mm,
        WIDTH,
        A4[1] - MARGIN - 18 * mm,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="cv", frames=[frame])])
    doc.build(story, canvasmaker=numbered)
    return buf.getvalue()
