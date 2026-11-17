"""A sample import workbook staff can download, fill in and upload.

Sheet 1 ("Data") is what the importer reads (first sheet, headers in row 1); its headers are the
PI 360 field names, so the wizard maps every column on its own. The other sheets are for people:
what each column means and which codes are valid right now. Nothing here touches the database
except reading the live programme, cohort and course codes.
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from apps.participants import services as participants

from . import placement_rows

# field -> (what to type, example)
PARTICIPANT_HELP = {
    "full_name": ("The person's full name as on their ID.", "Wanjiru Mwangi"),
    "programme_code": ("Code of the programme. See the Codes sheet.", "GO-BLUE"),
    "cohort_code": ("Code of the cohort (an intake at one institution). See Codes.", "GB-2026-A"),
    "course_code": ("Code of the course. See the Codes sheet.", "CARPENTRY"),
    "enrollment_no": (
        "Their number in the programme. Must be unique within the programme.",
        "GB/0001/26",
    ),
    "gender": ("female, male or other. Anything else becomes unknown.", "female"),
    "age": ("Whole years.", "21"),
    "county_code": ("The county name or code, e.g. Kisumu or 42.", "Kisumu"),
    "phone": ("A phone number, e.g. 0712345678.", "0712345678"),
    "email": ("An email address.", "wanjiru@example.com"),
    "status": ("active, completed or withdrawn.", "active"),
    "source_id": ("Your own reference for this person, if you have one.", ""),
}
PLACEMENT_HELP = {
    "programme_code": ("Code of the programme. See the Codes sheet.", "GO-BLUE"),
    "enrollment_no": (
        "The enrollment number already loaded for this person. Placements are held for "
        "numbers that are not on file.",
        "GB/0001/26",
    ),
    "placement_status": ("Where the placement stands, in your own words.", "Placed"),
    "organisation": ("Employer or organisation name.", "Acme Builders Ltd"),
    "address": ("Employer's physical address.", "Industrial Area, Nairobi"),
    "designation": ("The role the person was placed in.", "Assistant carpenter"),
    "placement_date": ("A date such as 2026-03-15 or 15/03/2026.", "2026-03-15"),
    "benefits": ("Any benefits offered.", "Lunch and transport"),
    "contact_name": ("Contact person at the employer.", "Peter Otieno"),
    "contact_phone": ("Contact person's phone.", "0722000000"),
    "contact_email": ("Contact person's email.", "hr@acme.example"),
}

HEAD = Font(bold=True, color="FFFFFF")
FILL = PatternFill("solid", fgColor="1F4E79")
NOTE = Font(italic=True, color="666666")


def _target(target):
    if target == "placements":
        return placement_rows.FIELDS, PLACEMENT_HELP
    return participants.FIELDS, PARTICIPANT_HELP


def _header(ws, row, labels):
    for i, label in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=label)
        c.font, c.fill = HEAD, FILL


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build_xlsx(target="participants") -> bytes:
    fields, help_ = _target(target)
    wb = Workbook()

    data = wb.active
    data.title = "Data"
    _header(data, 1, list(fields))
    # One example row so the format is obvious; the Instructions sheet says to replace it.
    for i, f in enumerate(fields, 1):
        data.cell(row=2, column=i, value=help_[f][1])
        data.cell(row=2, column=i).font = NOTE
    _widths(data, [max(len(f), len(help_[f][1])) + 4 for f in fields])
    data.freeze_panes = "A2"

    guide = wb.create_sheet("Instructions")
    guide["A1"] = "How to fill this sheet"
    guide["A1"].font = Font(bold=True, size=14)
    steps = [
        "1. Go to the Data sheet. Row 1 holds the column names: do not rename or reorder them.",
        "2. Row 2 is an example. Replace it with your first person, or delete it.",
        "3. One person per row. Add as many rows as you need.",
        "4. Columns marked Required must be filled on every row, or that row is held back.",
        "5. Use the codes on the Codes sheet for programme, cohort and course.",
        "6. Save as Excel (.xlsx) or CSV, then choose it under New import in PI 360.",
        "Nothing is saved until you have seen the check results and approved the import.",
    ]
    for i, s in enumerate(steps, 3):
        guide.cell(row=i, column=1, value=s)
    top = len(steps) + 4
    _header(guide, top, ["Column", "Required?", "What to put there", "Example"])
    for i, (f, req) in enumerate(fields.items(), top + 1):
        guide.cell(row=i, column=1, value=f)
        guide.cell(row=i, column=2, value="Required" if req else "Optional")
        guide.cell(row=i, column=3, value=help_[f][0])
        guide.cell(row=i, column=4, value=help_[f][1])
        guide.cell(row=i, column=3).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(guide, [22, 12, 70, 24])

    codes = wb.create_sheet("Codes")
    ref = participants.reference_codes()
    _header(codes, 1, ["Kind", "Code", "Name", "Programme"])
    r = 2
    for kind, label in (
        ("programme_code", "Programme"),
        ("cohort_code", "Cohort"),
        ("course_code", "Course"),
    ):
        for o in ref.get(kind, []):
            for col, v in enumerate((label, o["code"], o["name"], o.get("programme", "")), 1):
                codes.cell(row=r, column=col, value=v)
            r += 1
    _widths(codes, [12, 22, 44, 18])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
