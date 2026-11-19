# ruff: noqa: E501
"""The Excel and PDF files for a report. Built from the same data the page shows (``reports.build``)
and sent straight back; nothing is stored. Counts only: the files hold no name or contact detail."""

import io
import re
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.audit import services as audit

from . import reports
from .exports import _clean

PALETTE = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]
CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return _clean(v)


def _text(v) -> str:
    if v is None:
        return "Not enough data"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _tile_text(t) -> str:
    if t["value"] is None:
        return "Not enough data"
    return f"{_text(t['value'])}{t['unit']}"


def filename(report: dict, fmt: str) -> str:
    return f"{report['slug']}-{report['generated_on']}.{fmt}"


# --- Excel --------------------------------------------------------------------------------------

HEAD_FILL = PatternFill("solid", fgColor="1E3A8A")
HEAD_FONT = Font(bold=True, color="FFFFFF")


def _sheet_name(wb, title) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", title).strip()[:28] or "Sheet"
    name, n = base, 2
    while name in wb.sheetnames:
        name = f"{base[:26]} {n}"
        n += 1
    return name


def _write_table(ws, row, columns, rows):
    for c, label in enumerate(columns, 1):
        cell = ws.cell(row=row, column=c, value=label)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for r, values in enumerate(rows, row + 1):
        for c, v in enumerate(values, 1):
            ws.cell(row=r, column=c, value=_cell(v))
    return row + len(rows) + 1


def _widths(ws, widest=60):
    sizes: dict[int, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                sizes[cell.column] = max(
                    sizes.get(cell.column, 8), min(len(str(cell.value)) + 2, widest)
                )
    for col, size in sizes.items():
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = size


def _native_chart(ch, ws, top, n_rows):
    """A native Excel chart over the block written at rows ``top`` (header) to ``top + n_rows``."""
    kind = ch["type"]
    if kind == "pie":
        chart = PieChart()
    elif kind == "line":
        chart = LineChart()
    else:
        chart = BarChart()
        chart.type = "bar" if kind == "bar" else "col"
        if kind == "stacked":
            chart.grouping, chart.overlap = "stacked", 100
    chart.title = ch["title"]
    n_series = len(ch["series"])
    data = Reference(ws, min_col=2, max_col=1 + n_series, min_row=top, max_row=top + n_rows)
    cats = Reference(ws, min_col=1, min_row=top + 1, max_row=top + n_rows)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.height, chart.width = 8, 16
    return chart


def xlsx(report: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = report["title"]
    ws["A1"].font = Font(bold=True, size=16)
    ws["A2"] = report["purpose"]
    ws["A3"] = f"Generated on {report['generated_on']}"
    row = 5
    ws.cell(row=row, column=1, value="Filters used").font = Font(bold=True)
    row += 1
    if report["filters_applied"]:
        for f in report["filters_applied"]:
            ws.cell(row=row, column=1, value=f["label"])
            ws.cell(row=row, column=2, value=_cell(f["value"]))
            row += 1
    else:
        ws.cell(row=row, column=1, value="None: all records you can see")
        row += 1
    row += 1
    ws.cell(row=row, column=1, value="Headline numbers").font = Font(bold=True)
    row += 1
    for t in report["tiles"]:
        ws.cell(row=row, column=1, value=t["label"])
        ws.cell(
            row=row,
            column=2,
            value=_cell(t["value"]) if t["value"] is not None else "Not enough data",
        )
        if t["unit"]:
            ws.cell(row=row, column=3, value=t["unit"])
        if t["hint"]:
            ws.cell(row=row, column=4, value=t["hint"])
        row += 1
    for note in report["notes"]:
        row += 1
        ws.cell(row=row, column=1, value=f"Note: {note}")
    _widths(ws)

    for t in report["tables"]:
        sheet = wb.create_sheet(_sheet_name(wb, t["title"]))
        sheet["A1"] = t["title"]
        sheet["A1"].font = Font(bold=True, size=13)
        if t["rows"]:
            _write_table(sheet, 3, t["columns"], t["rows"])
        else:
            sheet["A3"] = "Nothing matches these filters."
        _widths(sheet)
        sheet.freeze_panes = "A4"

    charts = wb.create_sheet(_sheet_name(wb, "Charts"))
    top = 1
    for ch in report["charts"]:
        charts.cell(row=top, column=1, value=ch["title"]).font = Font(bold=True)
        if not ch["categories"]:
            charts.cell(
                row=top + 1, column=1, value=ch["empty"] or "Nothing matches these filters."
            )
            top += 4
            continue
        head = top + 1
        columns = ["", *[s["name"] for s in ch["series"]]]
        rows = [
            [cat, *[s["values"][i] for s in ch["series"]]] for i, cat in enumerate(ch["categories"])
        ]
        _write_table(charts, head, columns, rows)
        anchor = f"{chr(ord('A') + len(columns) + 1)}{top}"
        charts.add_chart(_native_chart(ch, charts, head, len(rows)), anchor)
        top = head + max(len(rows) + 2, 18)
    _widths(charts, widest=40)

    d = wb.create_sheet("Definitions")
    d["A1"] = "How these numbers are worked out"
    d["A1"].font = Font(bold=True, size=13)
    end = _write_table(
        d, 3, ["Name", "Meaning", "Signed off"],
        [[x["name"], x["meaning"], "Yes" if x["approved"] else "Working definition"] for x in report["definitions"]],
    )  # fmt: skip
    d.column_dimensions["A"].width = 26
    d.column_dimensions["B"].width = 100
    d.column_dimensions["C"].width = 20
    for r in range(4, end + 1):
        d.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- PDF ----------------------------------------------------------------------------------------

W = A4[0] - 30 * mm


def _num(v):
    return 0 if v is None else v


def _drawing(ch) -> Drawing | None:
    if not ch["categories"]:
        return None
    kind, cats = ch["type"], [str(c)[:28] for c in ch["categories"]]
    series = [[_num(v) for v in s["values"]] for s in ch["series"]]
    n_series = len(series)
    if kind == "pie":
        d = Drawing(W, 150)
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = 20, 15, 120, 120
        pie.data, pie.labels = series[0], None
        for i in range(len(cats)):
            pie.slices[i].fillColor = colors.HexColor(PALETTE[i % len(PALETTE)])
        d.add(pie)
        legend = Legend()
        legend.x, legend.y, legend.fontSize = 170, 130, 8
        legend.alignment, legend.deltay, legend.columnMaximum = "right", 11, 10
        legend.colorNamePairs = [
            (colors.HexColor(PALETTE[i % len(PALETTE)]), f"{c} ({series[0][i]:g})")
            for i, c in enumerate(cats)
        ]
        d.add(legend)
        return d
    if kind == "line":
        d = Drawing(W, 170)
        c = HorizontalLineChart()
        c.x, c.y, c.width, c.height = 40, 40, W - 70, 110
        c.data = series
        c.categoryAxis.categoryNames = cats
        c.categoryAxis.labels.angle, c.categoryAxis.labels.dy = 40, -12
        c.categoryAxis.labels.fontSize = c.valueAxis.labels.fontSize = 7
        c.valueAxis.valueMin = 0
        for i in range(n_series):
            c.lines[i].strokeColor = colors.HexColor(PALETTE[i % len(PALETTE)])
            c.lines[i].strokeWidth = 1.6
        d.add(c)
    else:
        horizontal = kind == "bar"
        height = max(120, 22 * len(cats) + 40) if horizontal else 170
        d = Drawing(W, height)
        c = HorizontalBarChart() if horizontal else VerticalBarChart()
        if horizontal:
            c.x, c.y, c.width, c.height = 150, 25, W - 190, height - 40
        else:
            c.x, c.y, c.width, c.height = 40, 40, W - 70, 110
        c.data = series
        c.categoryAxis.categoryNames = cats
        c.categoryAxis.labels.fontSize = c.valueAxis.labels.fontSize = 7
        if not horizontal:
            c.categoryAxis.labels.angle, c.categoryAxis.labels.dy = 30, -10
            c.categoryAxis.labels.boxAnchor = "ne"
        c.valueAxis.valueMin = 0
        if kind == "stacked":
            c.categoryAxis.style = "stacked"
        for i in range(n_series):
            c.bars[i].fillColor = colors.HexColor(PALETTE[i % len(PALETTE)])
        c.bars.strokeColor = None
        d.add(c)
    if n_series > 1:
        legend = Legend()
        legend.x, legend.y, legend.fontSize, legend.alignment = 40, d.height - 4, 8, "right"
        legend.columnMaximum = 1
        legend.deltax = 90
        legend.colorNamePairs = [
            (colors.HexColor(PALETTE[i % len(PALETTE)]), s["name"])
            for i, s in enumerate(ch["series"])
        ]
        d.add(legend)
    return d


def pdf(report: dict) -> bytes:
    base = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=base["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#4b5563"))
    h1 = ParagraphStyle("h1", parent=base["Title"], fontSize=18, alignment=0, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
    cellp = ParagraphStyle("c", parent=body, fontSize=8, leading=10)

    def p(text, style=body):
        return Paragraph(escape(str(text)), style)

    story = [p(report["title"], h1), p(report["purpose"], body)]
    filters = (
        "; ".join(f"{f['label']}: {f['value']}" for f in report["filters_applied"])
        or "none, all records you can see"
    )
    story += [
        p(f"Filters: {filters}", small),
        p(f"Generated on {report['generated_on']}", small),
        Spacer(1, 6),
    ]

    tiles = report["tiles"]
    row_vals = [[p(_tile_text(t), ParagraphStyle("v", parent=body, fontSize=14, leading=17, fontName="Helvetica-Bold")) for t in tiles],
                [p(t["label"], small) for t in tiles]]  # fmt: skip
    tile_table = Table(row_vals, colWidths=[W / len(tiles)] * len(tiles))
    tile_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")), ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))  # fmt: skip
    story += [tile_table]
    for note in report["notes"]:
        story.append(p(f"Note: {note}", small))

    for ch in report["charts"]:
        d = _drawing(ch)
        block = [p(ch["title"], h2)]
        block.append(d if d else p(ch["empty"] or "Nothing matches these filters.", small))
        story.append(KeepTogether(block))

    for t in report["tables"]:
        story.append(p(t["title"], h2))
        if not t["rows"]:
            story.append(p("Nothing matches these filters.", small))
            continue
        data = [
            [
                p(
                    c,
                    ParagraphStyle(
                        "th", parent=cellp, fontName="Helvetica-Bold", textColor=colors.white
                    ),
                )
                for c in t["columns"]
            ]
        ]
        data += [[p(_text(v) if v is not None else "", cellp) for v in r] for r in t["rows"]]
        n = len(t["columns"])
        first = W * (0.32 if n > 4 else 0.4)
        widths = [first] + [(W - first) / (n - 1)] * (n - 1) if n > 1 else [W]
        tbl = Table(data, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))  # fmt: skip
        story.append(tbl)

    story.append(p("How these numbers are worked out", h2))
    for x in report["definitions"]:
        tag = "" if x["approved"] else " (working definition, not yet signed off)"
        story.append(p(f"{x['name']}{tag}: {x['meaning']}", small))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(
            15 * mm,
            8 * mm,
            f"CAP-YEI Placement Intelligence 360 · {report['title']} · {report['generated_on']}",
        )
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=report["title"],
        author="CAP-YEI Placement Intelligence 360",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def render(report: dict, fmt: str) -> bytes:
    return xlsx(report) if fmt == "xlsx" else pdf(report)


def export_report(*, actor, slug, params, fmt):
    """Build one report file for ``actor`` and audit it. Returns ``(content, filename, rows)``,
    or ``None`` for an unknown report. Raises ``reports.FilterError`` for a bad filter. Nothing is
    stored, and the audit entry holds the report, filters and counts only, never a figure's rows."""
    report = reports.build(actor, slug, params)
    if report is None:
        return None
    content = render(report, fmt)
    rows = sum(len(t["rows"]) for t in report["tables"])
    audit.record(
        actor=actor,
        action="report.exported",
        object_type="report",
        object_id=slug,
        after={
            "report": slug,
            "format": fmt,
            "filters": {f["key"]: f["value"] for f in report["filters_applied"]},
            "rows": rows,
        },
    )
    return content, filename(report, fmt), rows
