# ruff: noqa: E501
"""The five stakeholder reports (Insight > Reports).

Each report is a function of the signed-in user and a set of filters. It returns plain data (tiles,
charts, tables, notes) that the page draws and the PDF and Excel files repeat, so the screen and
the files cannot disagree. Every number comes from the same facts the dashboard uses, drawn from
what the user may see, so a report with no filters matches the dashboard for "all time".

Reports show true numbers: no small-number hiding. They hold counts only, never a name or contact
detail of a youth, so anyone with ``reports.view_aggregate`` may open them."""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median

from apps.employers import services as employers
from apps.participants import services as participants
from apps.placements import services as placements
from apps.referrals import services as referrals

from .services import AGE_BANDS, GENDERS, METRICS, PLACED_STAGES, _age, _band, _pct, outcomes

PATHWAYS = [
    ("wage", "Wage employment"),
    ("self_employment", "Self-employment or entrepreneurship"),
    ("work_based_learning", "Work-based learning"),
    ("further_training", "Further training"),
]
STAGES = [
    ("submitted", "Submitted"),
    ("under_review", "Under review"),
    ("interview", "Interview"),
    ("selected", "Selected"),
    ("placed", "Placed"),
    ("rejected", "Rejected"),
    ("withdrawn", "Withdrawn"),
    ("no_response", "No response"),
    ("closed", "Closed"),
]
IN_PROGRESS = {"submitted", "under_review", "interview", "selected"}
WAIT_BANDS = [("Within 2 weeks", 0, 14), ("2 to 4 weeks", 15, 30), ("1 to 2 months", 31, 60), ("2 to 3 months", 61, 90), ("Over 3 months", 91, 10_000)]  # fmt: skip
ID_FILTERS = ("project", "cohort", "institution", "county", "sector", "employer")
ENROLMENT_FILTERS = ("project", "cohort", "institution")


class FilterError(ValueError):
    """A filter value that cannot be used; ``field`` names the filter, ``message`` is for the user."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    project: str = ""
    cohort: str = ""
    institution: str = ""
    county: str = ""
    sector: str = ""
    employer: str = ""
    pathway: str = ""
    gender: str = ""
    stage: str = ""
    checkin: str = ""

    @property
    def has_period(self):
        return bool(self.date_from or self.date_to)


def parse_filters(params) -> Filters:
    """Read filters from a query string. An unusable value is an error, never silently ignored,
    so a figure is never shown for a filter the reader thinks is on but is not."""
    f = Filters()
    for key, attr in (("from", "date_from"), ("to", "date_to")):
        raw = (params.get(key) or "").strip()
        if raw:
            try:
                setattr(f, attr, date.fromisoformat(raw))
            except ValueError:
                raise FilterError(
                    key, "Give dates as year-month-day, for example 2022-01-31."
                ) from None
    if f.date_from and f.date_to and f.date_from > f.date_to:
        raise FilterError("from", "The start date is after the end date.")
    for key in ID_FILTERS:
        raw = (params.get(key) or "").strip()
        if raw:
            try:
                setattr(f, key, str(uuid.UUID(raw)))
            except ValueError:
                raise FilterError(key, f"That {key} is not one this system knows.") from None
    choices = {
        "pathway": {c for c, _ in PATHWAYS},
        "gender": {c for c, _ in GENDERS},
        "stage": {c for c, _ in STAGES},
    }
    for key, allowed in choices.items():
        raw = (params.get(key) or "").strip()
        if raw:
            if raw not in allowed:
                raise FilterError(key, f"'{raw}' is not a choice for {key}.")
            setattr(f, key, raw)
    raw = (params.get("checkin") or "").strip()
    if raw:
        if not raw.isdigit():
            raise FilterError("checkin", "Pick a check-in point from the list.")
        f.checkin = raw
    return f


# --- shared helpers -----------------------------------------------------------------------------


def _in_period(d, f: Filters) -> bool:
    if not f.has_period:
        return True
    if d is None:
        return False
    if isinstance(d, datetime):
        d = d.date()
    return not ((f.date_from and d < f.date_from) or (f.date_to and d > f.date_to))


def _month(d):
    return d.strftime("%Y-%m")


def _month_span(months, cap=36):
    """Every month from the first to the last present, no gaps, at most ``cap`` of the latest."""
    if not months:
        return []
    first, last = min(months), max(months)
    y, m = int(first[:4]), int(first[5:])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out[-cap:]


def _tile(id, label, value, unit="", hint=""):
    return {"id": id, "label": label, "value": value, "unit": unit, "hint": hint}


def _chart(id, title, type, categories, series, unit="", empty=""):
    return {
        "id": id,
        "title": title,
        "type": type,
        "categories": categories,
        "series": [{"name": n, "values": v} for n, v in series],
        "unit": unit,
        "empty": empty,
    }


def _table(id, title, columns, rows):
    return {"id": id, "title": title, "columns": columns, "rows": rows}


def _defs(*names, extra=()):
    by_name = {n: (n, m, a) for n, m, a in METRICS}
    rows = [by_name[n] for n in names if n in by_name] + list(extra)
    return [{"name": n, "meaning": m, "approved": a} for n, m, a in rows]


class Ctx:
    """Everything a report reads, gathered once for the signed-in user."""

    def __init__(self, user, today):
        self.user, self.today = user, today
        self.opts = participants.report_options()
        self.cohorts = {c["id"]: c for c in self.opts["cohorts"]}
        self.youth = {y["id"]: y for y in participants.report_facts(user)}
        self.ids = set(self.youth)
        self.enrs = participants.enrollment_facts(user)
        self.refs = referrals.report_facts(user)
        self.referred, self.placed, recs = outcomes(user, self.ids, self.refs, True)
        owners = participants.enrollment_owners(user)
        emp = employers.report_facts()
        self.emp = emp
        self.emp_by_id = {e["id"]: e for e in emp["employers"]}
        self.opp_by_id = {o["id"]: o for o in emp["opportunities"]}
        self.names = {}
        self.events = self._events(recs, owners)
        self.rec_by_placement = {
            p["id"]: {"youth": owners[p["enrollment_id"]], "on": p["on"], "pathway": p["pathway"]}
            for p in recs
        }

    def sector_ids_of(self, employer_id):
        return self.emp["sectors_of"].get(employer_id, [])

    def employer_name(self, employer_id):
        if employer_id not in self.names:
            self.names.update(employers.employer_names())
        return self.names.get(employer_id, "")

    def _events(self, recs, owners):
        """One event per placement record, plus one per youth placed only through a referral."""
        events, has_record = [], set()
        for p in recs:
            yid = owners[p["enrollment_id"]]
            has_record.add(yid)
            events.append(
                {
                    "youth": yid,
                    "on": p["on"],
                    "pathway": p["pathway"] or "",
                    "employer_id": p["employer_id"],
                    "employer_name": p["employer_name"] or "",
                    "referred_at": None,
                }
            )
        placed_refs = sorted(
            (
                r
                for r in self.refs
                if (r["stage"] in PLACED_STAGES or (r["stage"] == "closed" and r["placed_at"]))
                and r["participant_id"] in self.ids
            ),
            key=lambda r: r["placed_at"] or r["updated_at"],
        )
        for r in placed_refs:
            if r["participant_id"] in has_record:
                continue
            has_record.add(r["participant_id"])
            opp = self.opp_by_id.get(r["opportunity_id"])
            events.append(
                {
                    "youth": r["participant_id"],
                    "on": (r["placed_at"] or r["updated_at"]).date(),
                    "pathway": "",
                    "employer_id": opp["employer_id"] if opp else None,
                    "employer_name": "",
                    "referred_at": r["referred_at"],
                }
            )
        return events

    def intake_on(self, e):
        c = self.cohorts.get(str(e["cohort_id"]))
        if e["enrolled_on"]:
            return e["enrolled_on"]
        if c and c["start"]:
            return date.fromisoformat(c["start"])
        return date(c["intake_year"], 1, 1) if c else None


def _enrolments(ctx: Ctx, f: Filters, *, period: bool):
    """The enrolments that pass the project, cohort, institution (and, if asked, intake period)
    filters. ``None`` when none of those filters is on, so every youth stays in."""
    use_period = period and f.has_period
    if not (any(getattr(f, k) for k in ENROLMENT_FILTERS) or use_period):
        return None
    out = []
    for e in ctx.enrs:
        if f.project and str(e["project_id"]) != f.project:
            continue
        if f.cohort and str(e["cohort_id"]) != f.cohort:
            continue
        if f.institution and str(e["institution_id"]) != f.institution:
            continue
        if use_period and not _in_period(ctx.intake_on(e), f):
            continue
        out.append(e)
    return out


def _youth_ids(ctx: Ctx, f: Filters, *, period: bool, gender=True):
    """Youth that pass the county, gender and enrolment filters, and the matching enrolments."""
    ids = set(ctx.ids)
    if f.county:
        ids = {i for i in ids if str(ctx.youth[i]["county_id"] or "") == f.county}
    if gender and f.gender:
        ids = {i for i in ids if ctx.youth[i]["gender"] == f.gender}
    enrs = _enrolments(ctx, f, period=period)
    if enrs is not None:
        ids &= {e["participant_id"] for e in enrs}
    return ids, enrs


def _name_maps(ctx: Ctx):
    o = ctx.opts
    return {
        "project": {r["id"]: r["name"] for r in o["projects"]},
        "cohort": {r["id"]: r["name"] for r in o["cohorts"]},
        "institution": {r["id"]: r["name"] for r in o["institutions"]},
        "county": {r["id"]: r["name"] for r in o["counties"]},
        "sector": {r["id"]: r["name"] for r in o["sectors"]},
    }


LABELS = {
    "project": "Project",
    "cohort": "Cohort",
    "institution": "Training institution",
    "county": "County",
    "sector": "Sector",
    "employer": "Employer",
    "pathway": "Pathway",
    "gender": "Gender",
    "stage": "Referral stage",
    "checkin": "Check-in point",
}


def _applied(ctx: Ctx, f: Filters, keys) -> list[dict]:
    """The filters in force, in words, for the page header and the files."""
    names = _name_maps(ctx)
    out = []
    if "period" in keys and f.has_period:
        a, b = f.date_from, f.date_to
        text = f"{a.isoformat() if a else 'start'} to {b.isoformat() if b else 'today'}"
        out.append({"key": "period", "label": "Period", "value": text})
    for key in keys:
        if key == "period":
            continue
        raw = getattr(f, key)
        if not raw:
            continue
        if key in names:
            value = names[key].get(raw, raw)
        elif key == "employer":
            value = ctx.employer_name(uuid.UUID(raw)) or raw
        elif key == "pathway":
            value = dict(PATHWAYS)[raw]
        elif key == "gender":
            value = dict(GENDERS)[raw]
        elif key == "stage":
            value = dict(STAGES)[raw]
        else:
            value = _point_label(int(raw))
        out.append({"key": key, "label": LABELS[key], "value": value})
    return out


def _point_label(days: int) -> str:
    if days < 180:
        return f"{days} days"
    months = round(days / 30.4)
    return f"{months} months"


def _group_row(label, reg, ref, plc):
    return [label, reg, ref, plc, _pct(plc, reg)]


# --- 1. Project scorecard -------------------------------------------------------------------


def project_scorecard(ctx: Ctx, f: Filters) -> dict:
    ids, enrs = _youth_ids(ctx, f, period=True)
    referred, placed = ids & ctx.referred, ids & ctx.placed
    enrolled_all = {e["participant_id"] for e in ctx.enrs}
    enrolled = ids & enrolled_all
    cohort_name = _name_maps(ctx)["cohort"]
    prog_name = _name_maps(ctx)["project"]
    inst_name = _name_maps(ctx)["institution"]

    # One row per cohort: the youth enrolled in it who pass the filters.
    by_cohort: dict[str, set] = {}
    for e in enrs if enrs is not None else ctx.enrs:
        if e["participant_id"] in ids:
            by_cohort.setdefault(str(e["cohort_id"]), set()).add(e["participant_id"])
    cohort_rows = []
    for cid, members in by_cohort.items():
        c = ctx.cohorts.get(cid, {})
        cohort_rows.append(
            [
                cohort_name.get(cid, "Cohort not recorded"),
                prog_name.get(c.get("project_id"), ""),
                inst_name.get(c.get("institution_id"), ""),
                c.get("intake_year") or "",
                len(members),
                len(members & ctx.referred),
                len(members & ctx.placed),
                _pct(len(members & ctx.placed), len(members)),
            ]
        )
    cohort_rows.sort(key=lambda r: (-(r[3] or 0), r[0]))

    year_enrolled, year_placed = Counter(), Counter()
    for cid, members in by_cohort.items():
        year = (ctx.cohorts.get(cid) or {}).get("intake_year") or 0
        year_enrolled[year] += len(members)
        year_placed[year] += len(members & ctx.placed)
    years = sorted(year_enrolled)

    county_reg, county_placed = Counter(), Counter()
    county_ref = Counter()
    for i in ids:
        k = ctx.youth[i]["county"] or "County not recorded"
        county_reg[k] += 1
        county_placed[k] += i in ctx.placed
        county_ref[k] += i in ctx.referred
    top = [k for k, _ in county_reg.most_common(10)]

    return {
        "tiles": [
            _tile(
                "registered",
                "Youth in scope",
                len(ids),
                hint="Registered youth who match the filters",
            ),
            _tile(
                "enrolled",
                "Enrolled in training",
                len(enrolled),
                hint="Have at least one project enrolment",
            ),
            _tile("referred", "Referred to employers", len(referred)),
            _tile("placed", "Placed", len(placed)),
            _tile(
                "rate",
                "Placement rate",
                _pct(len(placed), len(ids)),
                "%",
                "Placed divided by youth in scope",
            ),
        ],
        "charts": [
            _chart(
                "funnel",
                "From registration to placement",
                "bar",
                ["Registered", "Referred", "Placed"],
                [("Youth", [len(ids), len(referred), len(placed)])],
            ),
            _chart(
                "by-year",
                "Enrolled and placed by intake year",
                "column",
                [str(y) if y else "Year not recorded" for y in years],
                [
                    ("Enrolled", [year_enrolled[y] for y in years]),
                    ("Placed", [year_placed[y] for y in years]),
                ],
                empty="No enrolments match these filters.",
            ),
            _chart(
                "by-county",
                "Registered and placed, ten largest counties",
                "bar",
                top,
                [
                    ("Registered", [county_reg[k] for k in top]),
                    ("Placed", [county_placed[k] for k in top]),
                ],
                empty="No youth match these filters.",
            ),
        ],
        "tables": [
            _table(
                "cohorts",
                "By cohort",
                [
                    "Cohort",
                    "Project",
                    "Training institution",
                    "Intake year",
                    "Enrolled",
                    "Referred",
                    "Placed",
                    "Placement rate (%)",
                ],
                cohort_rows,
            ),
            _table(
                "counties",
                "By county of origin",
                ["County", "Registered", "Referred", "Placed", "Placement rate (%)"],
                sorted(
                    (
                        _group_row(k, county_reg[k], county_ref[k], county_placed[k])
                        for k in county_reg
                    ),
                    key=lambda r: -r[1],
                ),
            ),
        ],
        "definitions": _defs(
            "Registered youth",
            "Placed",
            "Placement rate",
            "Referred",
            extra=[
                (
                    "Period",
                    "The period filters the date each youth's cohort started: the enrolment date, else the cohort start date, else 1 January of its intake year.",
                    False,
                ),
                (
                    "Cohort rows",
                    "A youth enrolled in two cohorts appears in both rows but only once in the tiles and charts.",
                    True,
                ),
            ],
        ),
        "notes": [],
    }


# --- 2. Placement outcomes --------------------------------------------------------------------


def placement_outcomes(ctx: Ctx, f: Filters) -> dict:
    ids, _ = _youth_ids(ctx, f, period=False, gender=False)
    events = []
    for e in ctx.events:
        if e["youth"] not in ids or not _in_period(e["on"], f):
            continue
        if f.pathway and e["pathway"] != f.pathway:
            continue
        if f.employer and str(e["employer_id"] or "") != f.employer:
            continue
        sectors = [str(s) for s in ctx.sector_ids_of(e["employer_id"])] if e["employer_id"] else []
        if f.sector and f.sector not in sectors:
            continue
        events.append({**e, "sectors": sectors})

    youth_placed = {e["youth"] for e in events}
    sector_names = _name_maps(ctx)["sector"]
    pathway_names = dict(PATHWAYS)
    by_pathway = Counter(pathway_names.get(e["pathway"], "Pathway not recorded") for e in events)
    by_sector = Counter()
    for e in events:
        for s in e["sectors"] or [None]:
            by_sector[
                sector_names.get(s, "Sector not recorded") if s else "Sector not recorded"
            ] += 1
    per_month = Counter(_month(e["on"]) for e in events)
    months = _month_span(list(per_month))

    waits = []
    for r in ctx.refs:
        if (
            r["placed_at"]
            and r["referred_at"]
            and r["participant_id"] in youth_placed
            and _in_period(r["placed_at"], f)
        ):
            waits.append((r["placed_at"] - r["referred_at"]).days)
    bands = [sum(1 for w in waits if lo <= w <= hi) for _l, lo, hi in WAIT_BANDS]

    employer_rows: dict = {}
    for e in events:
        key = e["employer_id"] or (e["employer_name"].strip().lower() or None)
        name = ctx.employer_name(e["employer_id"]) if e["employer_id"] else e["employer_name"]
        row = employer_rows.setdefault(
            key,
            {
                "name": name or "Employer not recorded",
                "linked": bool(e["employer_id"]),
                "placements": 0,
                "youth": set(),
                "sectors": set(),
            },
        )
        row["placements"] += 1
        row["youth"].add(e["youth"])
        row["sectors"].update(sector_names.get(s, "") for s in e["sectors"])
    emp_table = sorted(
        (
            [
                r["name"],
                r["placements"],
                len(r["youth"]),
                ", ".join(sorted(x for x in r["sectors"] if x)) or "Sector not recorded",
                "Linked" if r["linked"] else "Name from source sheet",
            ]
            for r in employer_rows.values()
        ),
        key=lambda r: (-r[1], r[0]),
    )[:15]

    county_count, county_youth = Counter(), {}
    for e in events:
        k = ctx.youth[e["youth"]]["county"] or "County not recorded"
        county_count[k] += 1
        county_youth.setdefault(k, set()).add(e["youth"])

    linked = {e["employer_id"] for e in events if e["employer_id"]}
    return {
        "tiles": [
            _tile("youth", "Youth placed", len(youth_placed)),
            _tile(
                "placements",
                "Placements recorded",
                len(events),
                hint="A youth can have more than one",
            ),
            _tile(
                "employers", "Employers hiring", len(linked), hint="Employers linked to a placement"
            ),
            _tile(
                "wait",
                "Median days from referral to placement",
                median(waits) if waits else None,
                "days",
                "Only placements that came through a referral"
                if waits
                else "No placement came through a referral yet",
            ),
        ],
        "charts": [
            _chart(
                "pathway",
                "Placements by pathway",
                "pie",
                list(by_pathway),
                [("Placements", list(by_pathway.values()))],
                empty="No placements match these filters.",
            ),
            _chart(
                "sector",
                "Placements by sector",
                "bar",
                list(by_sector),
                [("Placements", list(by_sector.values()))],
                empty="No placements match these filters.",
            ),
            _chart(
                "per-month",
                "Placements per month",
                "line",
                months,
                [("Placements", [per_month.get(m, 0) for m in months])],
                empty="No placements match these filters.",
            ),
            _chart(
                "wait",
                "Time from referral to placement",
                "column",
                [b[0] for b in WAIT_BANDS],
                [("Placements", bands)],
                empty="No placement through a referral matches these filters.",
            ),
        ],
        "tables": [
            _table(
                "employers",
                "Employers by placements (top 15)",
                ["Employer", "Placements", "Youth", "Sectors", "Employer record"],
                emp_table,
            ),
            _table(
                "counties",
                "Placements by county of origin",
                ["County", "Placements", "Youth"],
                sorted(
                    ([k, v, len(county_youth[k])] for k, v in county_count.items()),
                    key=lambda r: -r[1],
                )[:15],
            ),
        ],
        "definitions": _defs(
            "Placed",
            "Time to placement",
            extra=[
                (
                    "Placement",
                    "A placement recorded as placed, or a youth whose referral reached the Placed stage and who has no placement record.",
                    False,
                ),
                (
                    "Period",
                    "The period filters the placement start date (the date the referral was placed, when there is no placement record).",
                    False,
                ),
                (
                    "Sector",
                    "The sectors of the employer. An employer in several sectors counts in each.",
                    True,
                ),
            ],
        ),
        "notes": [
            "Time from finishing training to placement is not shown: training completion dates are not reliably imported."
        ],
    }


# --- 3. Equity and reach ----------------------------------------------------------------------


SUPPRESSED = "Suppressed"


def suppress_small(rows: list[list], threshold: int) -> list[list]:
    """Hide the numbers of any group smaller than ``threshold`` (``exports.small_cell``). Rows are
    ``[label, registered, referred, placed, rate]``. A single hidden group could be worked out
    from the total, so when exactly one is hidden the next smallest is hidden too."""
    hidden = {i for i, r in enumerate(rows) if r[1] < threshold}
    if len(hidden) == 1 and len(rows) > 1:
        hidden.add(min((i for i in range(len(rows)) if i not in hidden), key=lambda i: rows[i][1]))
    return [
        [r[0], *([SUPPRESSED] * (len(r) - 1))] if i in hidden else r for i, r in enumerate(rows)
    ]


DISABILITY_GROUPS = [("yes", "Yes"), ("no", "No"), ("not_recorded", "Not recorded")]


def _disability_table(ctx: Ctx, ids, referred, placed):
    """Registered, referred and placed by disability, or ``None`` when the caller may not see it.
    "Not recorded" is its own group: nobody is assumed to be one or the other."""
    from apps.intelligence import services as intelligence

    answers = participants.disability_report_values(ctx.user, ids)
    if answers is None:
        return None
    reg, ref, plc = Counter(), Counter(), Counter()
    for i in ids:
        k = answers.get(i, "not_recorded")
        reg[k] += 1
        ref[k] += i in referred
        plc[k] += i in placed
    rows = [_group_row(label, reg[k], ref[k], plc[k]) for k, label in DISABILITY_GROUPS if reg[k]]
    return _table(
        "disability",
        "By disability",
        ["Disability", "Registered", "Referred", "Placed", "Placement rate (%)"],
        suppress_small(rows, intelligence.setting("exports.small_cell")),
    )


def equity_and_reach(ctx: Ctx, f: Filters) -> dict:
    ids, _ = _youth_ids(ctx, f, period=True)
    referred, placed = ids & ctx.referred, ids & ctx.placed
    disability_table = _disability_table(ctx, ids, referred, placed)

    def group(keyfn, order):
        reg, ref, plc = Counter(), Counter(), Counter()
        for i in ids:
            k = keyfn(i)
            reg[k] += 1
            ref[k] += i in referred
            plc[k] += i in placed
        keys = [k for k in order if reg.get(k)] + [k for k in reg if k not in order]
        return keys, reg, ref, plc

    g_keys, g_reg, g_ref, g_plc = group(lambda i: ctx.youth[i]["gender"], [g for g, _ in GENDERS])
    gname = dict(GENDERS)
    a_label = {k: lbl for k, lbl, *_ in [*AGE_BANDS, ("unknown", "Age not recorded")]}
    a_keys, a_reg, a_ref, a_plc = group(
        lambda i: _band(_age(ctx.youth[i], ctx.today)), [k for k, *_ in AGE_BANDS] + ["unknown"]
    )
    c_keys, c_reg, c_ref, c_plc = group(
        lambda i: ctx.youth[i]["county"] or "County not recorded", []
    )
    c_keys = sorted(c_keys, key=lambda k: -c_reg[k])

    def rate_series(keys, reg, plc):
        return [_pct(plc[k], reg[k]) for k in keys]

    female_reg, female_plc = g_reg.get("female", 0), g_plc.get("female", 0)
    male_reg, male_plc = g_reg.get("male", 0), g_plc.get("male", 0)
    top = c_keys[:10]
    return {
        "tiles": [
            _tile(
                "women-registered",
                "Women among registered youth",
                _pct(female_reg, len(ids)),
                "%",
                f"{female_reg} of {len(ids)}",
            ),
            _tile(
                "women-placed",
                "Women among placed youth",
                _pct(female_plc, len(placed)),
                "%",
                f"{female_plc} of {len(placed)}",
            ),
            _tile("rate-women", "Placement rate, women", _pct(female_plc, female_reg), "%"),
            _tile("rate-men", "Placement rate, men", _pct(male_plc, male_reg), "%"),
        ],
        "charts": [
            _chart(
                "gender",
                "Registered, referred and placed by gender",
                "column",
                [gname[k] for k in g_keys],
                [
                    ("Registered", [g_reg[k] for k in g_keys]),
                    ("Referred", [g_ref[k] for k in g_keys]),
                    ("Placed", [g_plc[k] for k in g_keys]),
                ],
                empty="No youth match these filters.",
            ),
            _chart(
                "gender-rate",
                "Placement rate by gender",
                "bar",
                [gname[k] for k in g_keys],
                [("Placement rate", rate_series(g_keys, g_reg, g_plc))],
                "%",
                "No youth match these filters.",
            ),
            _chart(
                "age",
                "Registered and placed by age band",
                "column",
                [a_label.get(k, k) for k in a_keys],
                [
                    ("Registered", [a_reg[k] for k in a_keys]),
                    ("Placed", [a_plc[k] for k in a_keys]),
                ],
                empty="No youth match these filters.",
            ),
            _chart(
                "county",
                "Placement rate, ten largest counties",
                "bar",
                top,
                [("Placement rate", rate_series(top, c_reg, c_plc))],
                "%",
                "No youth match these filters.",
            ),
        ],
        "tables": [
            _table(
                "gender",
                "By gender",
                ["Gender", "Registered", "Referred", "Placed", "Placement rate (%)"],
                [_group_row(gname[k], g_reg[k], g_ref[k], g_plc[k]) for k in g_keys],
            ),
            _table(
                "age",
                "By age band",
                ["Age band", "Registered", "Referred", "Placed", "Placement rate (%)"],
                [_group_row(a_label.get(k, k), a_reg[k], a_ref[k], a_plc[k]) for k in a_keys],
            ),
            _table(
                "county",
                "By county of origin",
                ["County", "Registered", "Referred", "Placed", "Placement rate (%)"],
                [_group_row(k, c_reg[k], c_ref[k], c_plc[k]) for k in c_keys],
            ),
            *([disability_table] if disability_table else []),
        ],
        "definitions": _defs(
            "Registered youth",
            "Placed",
            "Placement rate",
            extra=[
                (
                    "Age band",
                    "Age today, from the date of birth, or from the age on the source sheet moved forward by the years since.",
                    True,
                ),
                ("Period", "The period filters the date each youth's cohort started.", False),
            ],
        ),
        "notes": [
            *(
                [
                    "Disability is shown only to people allowed to see it. Groups smaller than the "
                    "small-group limit in Rules are hidden, and 'Not recorded' means nobody has "
                    "asked, not that the answer is No."
                ]
                if disability_table
                else ["Disability is not shown: it is off, or you do not have access to it."]
            ),
            "Gender is as recorded on the source sheets; 'Not recorded' means the sheet did not say.",
        ],
    }


# --- 4. Retention after placement ---------------------------------------------------------------


# B26 (PI360-NEW-037): retention at 3, 6 and 12 months, same employer and any employer apart.
RETENTION_POINTS = (90, 183, 365)
SPLIT_BUCKETS = (
    ("same", "Same employer"),
    ("other", "Another employer"),
    ("self", "Self-employed"),
    ("out", "Not working"),
)
RETENTION_SPLIT_DEFS = [
    (
        "Retention cohort (3, 6 and 12 months)",
        "Youth whose first recorded placement reached its 3-, 6- or 12-month check-in, and the check-in was completed. A job that followed a change of employer does not start a new cohort, so nobody is counted twice.",
        False,
    ),
    (
        "Same-employer retention",
        "Completed check-ins where the youth was still with the employer of that first placement, divided by completed check-ins at that point.",
        False,
    ),
    (
        "In work, any employer",
        "Completed check-ins where the youth was with the same employer or another employer, divided by completed check-ins. Self-employment is shown apart and not added in (B27).",
        False,
    ),
    (
        "Check-ins before outcomes were recorded",
        "A check-in completed before the four outcomes existed only says whether the youth was still employed: yes is counted as the same employer, no as not working.",
        False,
    ),
]


def _split_bucket(r) -> str | None:
    outcome = r.get("outcome") or ""
    if outcome:
        return {
            "same_employer": "same", "changed_employer": "other",
            "self_employed": "self", "left_employment": "out",
        }.get(outcome)  # fmt: skip
    if r["still_employed"] is None:
        return None
    return "same" if r["still_employed"] else "out"  # recorded before NEW-034


def _retention_split(rows, today, enough) -> dict:
    """Completed check-ins at 3, 6 and 12 months on first placements, by where the youth was."""
    counts = {p: {k: 0 for k, _ in SPLIT_BUCKETS} | {"done": 0} for p in RETENTION_POINTS}
    for r in rows:
        point = r["offset_days"]
        if point not in counts or not r.get("root", True) or r["due_date"] > today:
            continue
        if r["status"] != "done" or (bucket := _split_bucket(r)) is None:
            continue
        counts[point][bucket] += 1
        counts[point]["done"] += 1

    def rate(n, t):
        return _pct(n, t["done"]) if t["done"] >= enough else None

    def shown(v):
        return v if v is not None else "Not enough check-ins yet"

    labels = [_point_label(p) for p in RETENTION_POINTS]
    table = _table(
        "by-employer",
        "Retention at 3, 6 and 12 months: same employer or another",
        [
            "Check-in point", "Completed", *[label for _, label in SPLIT_BUCKETS],
            "Same employer (%)", "In work, any employer (%)",
        ],
        [
            [
                _point_label(p), t["done"], *[t[k] for k, _ in SPLIT_BUCKETS],
                shown(rate(t["same"], t)), shown(rate(t["same"] + t["other"], t)),
            ]
            for p, t in counts.items()
        ],
    )  # fmt: skip
    chart = _chart(
        "by-employer",
        "Where youth were at 3, 6 and 12 months",
        "stacked",
        labels,
        [(label, [counts[p][k] for p in RETENTION_POINTS]) for k, label in SPLIT_BUCKETS],
        empty="" if any(t["done"] for t in counts.values()) else "No completed check-ins yet.",
    )
    return {"table": table, "chart": chart, "counts": counts}


def retention(ctx: Ctx, f: Filters) -> dict:
    from apps.intelligence import services as intelligence

    ids, _ = _youth_ids(ctx, f, period=False, gender=False)
    enough = intelligence.setting("employer.min_retention_checks")
    pathway_names = dict(PATHWAYS)
    rows = []
    for fu in placements.followup_facts():
        rec = ctx.rec_by_placement.get(fu["placement_id"])
        if rec is None or rec["youth"] not in ids or not _in_period(rec["on"], f):
            continue
        if f.pathway and rec["pathway"] != f.pathway:
            continue
        if f.checkin and str(fu["offset_days"]) != f.checkin:
            continue
        rows.append({**fu, "pathway": rec["pathway"]})

    def tally(items):
        t = {
            "scheduled": 0,
            "due": 0,
            "done": 0,
            "kept": 0,
            "left": 0,
            "unreached": 0,
            "overdue": 0,
        }
        for r in items:
            if r["due_date"] > ctx.today:
                t["scheduled"] += 1
                continue
            t["due"] += 1
            if r["status"] == "done" and r["still_employed"] is not None:
                t["done"] += 1
                t["kept" if r["still_employed"] else "left"] += 1
            elif r["status"] == "unreachable":
                t["unreached"] += 1
            elif r["status"] == "open":
                t["overdue"] += 1
        t["rate"] = _pct(t["kept"], t["done"]) if t["done"] >= enough else None
        return t

    points = sorted({r["offset_days"] for r in rows if r["offset_days"] is not None})
    by_point = {p: tally([r for r in rows if r["offset_days"] == p]) for p in points}
    pathways = sorted({r["pathway"] for r in rows}, key=lambda p: pathway_names.get(p, "zz"))
    by_pathway = {p: tally([r for r in rows if r["pathway"] == p]) for p in pathways}
    total = tally(rows)

    def row(label, t):
        return [
            label,
            t["due"],
            t["done"],
            t["kept"],
            t["left"],
            t["unreached"],
            t["overdue"],
            t["rate"] if t["rate"] is not None else "Not enough check-ins yet",
        ]

    columns = [
        "Due so far",
        "Completed",
        "Still employed",
        "No longer employed",
        "Could not be reached",
        "Overdue",
        "Retention (%)",
    ]
    labels = [_point_label(p) for p in points]
    empty = "No check-ins have been recorded yet." if not rows else ""
    split = _retention_split(rows, ctx.today, enough)
    rate_hint = f"Shown once at least {enough} check-ins are complete (now {total['done']})"
    return {
        "tiles": [
            _tile(
                "placements", "Placements with check-ins", len({r["placement_id"] for r in rows})
            ),
            _tile(
                "done", "Check-ins completed", total["done"], hint=f"Of {total['due']} due so far"
            ),
            _tile(
                "retention",
                "Still employed at check-in",
                total["rate"],
                "%",
                rate_hint
                if total["rate"] is None
                else f"{total['kept']} of {total['done']} checked",
            ),
            _tile("overdue", "Overdue", total["overdue"], hint="Due, not yet done"),
        ],
        "charts": [
            _chart(
                "by-point",
                "Still employed, by check-in point",
                "column",
                labels,
                [("Still employed (%)", [by_point[p]["rate"] for p in points])],
                "%",
                empty or "Not enough completed check-ins at any point yet.",
            ),
            _chart(
                "results",
                "What each check-in found",
                "stacked",
                labels,
                [
                    ("Still employed", [by_point[p]["kept"] for p in points]),
                    ("No longer employed", [by_point[p]["left"] for p in points]),
                    ("Could not be reached", [by_point[p]["unreached"] for p in points]),
                    ("Overdue", [by_point[p]["overdue"] for p in points]),
                ],
                empty=empty,
            ),
            split["chart"],
            _chart(
                "by-pathway",
                "Still employed, by pathway",
                "bar",
                [pathway_names.get(p, "Pathway not recorded") for p in pathways],
                [("Still employed (%)", [by_pathway[p]["rate"] for p in pathways])],
                "%",
                empty or "Not enough completed check-ins yet.",
            ),
        ],
        "tables": [
            _table(
                "by-point",
                "By check-in point",
                ["Check-in point", *columns],
                [row(_point_label(p), by_point[p]) for p in points],
            ),
            _table(
                "by-pathway",
                "By pathway",
                ["Pathway", *columns],
                [
                    row(pathway_names.get(p, "Pathway not recorded"), by_pathway[p])
                    for p in pathways
                ],
            ),
            split["table"],
        ],
        "definitions": _defs(
            extra=[
                (
                    "Check-in",
                    "A follow-up call or visit with a placed youth, due a set number of days after the placement started. Cancelled check-ins are left out.",
                    True,
                ),
                (
                    "Still employed",
                    f"Completed check-ins where the youth was still employed, divided by completed check-ins. Shown only once at least {enough} check-ins are complete, so a handful of calls cannot look like a trend.",
                    False,
                ),
                (
                    "Could not be reached",
                    "A check-in marked unreachable. It is never counted as a job lost.",
                    True,
                ),
                ("Overdue", "A check-in past its due date that is still open.", True),
                *RETENTION_SPLIT_DEFS,
                ("Period", "The period filters the placement start date.", False),
            ]
        ),
        "notes": ["Retention beyond the scheduled check-ins is not measured."],
    }


# --- 5. Employer and pipeline health ------------------------------------------------------------


def employer_pipeline(ctx: Ctx, f: Filters) -> dict:
    from apps.intelligence import services as intelligence

    sector_names = _name_maps(ctx)["sector"]
    now = datetime.now().astimezone()

    def opp_sectors(o):
        return [str(s) for s in (o["sector_ids"] or ctx.sector_ids_of(o["employer_id"]))]

    def opp_counties(o):
        emp = ctx.emp_by_id.get(o["employer_id"])
        return [str(c) for c in (o["county_ids"] or (emp["county_ids"] if emp else []))]

    def opp_ok(o):
        if f.employer and str(o["employer_id"]) != f.employer:
            return False
        if f.sector and f.sector not in opp_sectors(o):
            return False
        return not (f.county and f.county not in opp_counties(o))

    refs = []
    for r in ctx.refs:
        o = ctx.opp_by_id.get(r["opportunity_id"])
        if o is None or not opp_ok(o) or not _in_period(r["referred_at"], f):
            continue
        if f.stage and r["stage"] != f.stage:
            continue
        refs.append(r)

    placed_refs = [
        r
        for r in refs
        if r["stage"] in PLACED_STAGES or (r["stage"] == "closed" and r["placed_at"])
    ]
    placed_ids = {r["id"] for r in placed_refs}
    stage_counts = Counter(r["stage"] for r in refs)
    stalled_days = intelligence.setting("support.stalled_days")
    cutoff = now - timedelta(days=stalled_days)
    stalled = [r for r in refs if r["stage"] in IN_PROGRESS and r["updated_at"] <= cutoff]
    stalled_ids = {r["id"] for r in stalled}

    emps = [e for e in ctx.emp["employers"] if (not f.employer or str(e["id"]) == f.employer) and (not f.sector or f.sector in [str(s) for s in e["sector_ids"]]) and (not f.county or f.county in [str(c) for c in e["county_ids"]])]  # fmt: skip
    open_opps = [o for o in ctx.emp["opportunities"] if o["status"] == "open" and opp_ok(o)]
    referred_opps = {r["opportunity_id"] for r in ctx.refs}
    no_referral = [o for o in open_opps if o["id"] not in referred_opps]

    sec_sub, sec_plc = Counter(), Counter()
    for r in refs:
        o = ctx.opp_by_id[r["opportunity_id"]]
        for s in opp_sectors(o) or [None]:
            label = sector_names.get(s, "Sector not recorded") if s else "Sector not recorded"
            sec_sub[label] += 1
            sec_plc[label] += r["id"] in placed_ids
    sectors = [k for k, _ in sec_sub.most_common(12)]

    sub_m = Counter(_month(r["referred_at"]) for r in refs if r["referred_at"])
    plc_m = Counter(_month(r["placed_at"]) for r in placed_refs if r["placed_at"])
    months = _month_span(list(sub_m | plc_m))

    # Per employer: open opportunities, referrals, placements, and referrals that have stalled.
    per_emp: dict = {}
    for o in open_opps:
        per_emp.setdefault(o["employer_id"], Counter())["opps"] += 1
    for r in refs:
        c = per_emp.setdefault(ctx.opp_by_id[r["opportunity_id"]]["employer_id"], Counter())
        c["refs"] += 1
        c["placed"] += r["id"] in placed_ids
        c["stalled"] += r["id"] in stalled_ids
    names = employers.employer_names(per_emp)
    emp_rows = sorted(
        (
            [
                names.get(k, "Employer not recorded"),
                c["opps"],
                c["refs"],
                c["placed"],
                _pct(c["placed"], c["refs"]),
            ]
            for k, c in per_emp.items()
        ),
        key=lambda r: (-r[3], -r[2], r[0]),
    )[:20]
    stalled_rows = sorted(
        (
            [names.get(k, "Employer not recorded"), c["stalled"]]
            for k, c in per_emp.items()
            if c["stalled"]
        ),
        key=lambda r: -r[1],
    )[:15]
    brief = employers.brief_opportunities(
        [
            o["id"]
            for o in sorted(no_referral, key=lambda o: (o["closing"] is None, o["closing"]))[:15]
        ]
    )
    no_ref_rows = []
    for o in sorted(no_referral, key=lambda o: (o["closing"] is None, o["closing"]))[:15]:
        info = brief.get(o["id"])
        if info:
            no_ref_rows.append(
                [
                    info["name"],
                    info["detail"].split(" · ")[0],
                    o["closing"].isoformat() if o["closing"] else "No closing date",
                ]
            )

    waits = [
        (r["placed_at"] - r["referred_at"]).days
        for r in placed_refs
        if r["placed_at"] and r["referred_at"]
    ]
    return {
        "tiles": [
            _tile("employers", "Active employers", len(emps)),
            _tile(
                "opps",
                "Open opportunities",
                len(open_opps),
                hint=f"{len(no_referral)} with no referral yet",
            ),
            _tile("referrals", "Referrals submitted", len(refs)),
            _tile(
                "conversion",
                "Referrals that led to a placement",
                _pct(len(placed_refs), len(refs)),
                "%",
                f"{len(placed_refs)} of {len(refs)}",
            ),
            _tile(
                "stalled",
                "Referrals with no movement",
                len(stalled),
                hint=f"In progress {stalled_days} days or more",
            ),
        ],
        "charts": [
            _chart(
                "pipeline",
                "Where referrals stand",
                "bar",
                [lbl for k, lbl in STAGES if stage_counts.get(k)],
                [("Referrals", [stage_counts[k] for k, _ in STAGES if stage_counts.get(k)])],
                empty="No referrals match these filters.",
            ),
            _chart(
                "sector",
                "Referrals and placements by sector",
                "bar",
                sectors,
                [
                    ("Referrals", [sec_sub[k] for k in sectors]),
                    ("Placed", [sec_plc[k] for k in sectors]),
                ],
                empty="No referrals match these filters.",
            ),
            _chart(
                "per-month",
                "Referrals and placements per month",
                "line",
                months,
                [
                    ("Referrals", [sub_m.get(m, 0) for m in months]),
                    ("Placed", [plc_m.get(m, 0) for m in months]),
                ],
                empty="No referrals match these filters.",
            ),
        ],
        "tables": [
            _table(
                "employers",
                "Employers by activity (top 20)",
                ["Employer", "Open opportunities", "Referrals", "Placed", "Conversion (%)"],
                emp_rows,
            ),
            _table(
                "stalled",
                "Referrals with no movement, by employer",
                ["Employer", "Referrals stalled"],
                stalled_rows,
            ),
            _table(
                "no-referral",
                "Open opportunities with no referral (15 closing first)",
                ["Opportunity", "Employer", "Closes"],
                no_ref_rows,
            ),
        ],
        "definitions": _defs(
            "Active employer",
            "Open opportunity",
            "Referral conversion",
            "Overdue referral",
            extra=[
                (
                    "Period",
                    "The period filters the date a referral was submitted. Open opportunities and stalled referrals are today's position, so the period does not change them.",
                    False,
                ),
                (
                    "Median wait",
                    f"Median days from submission to Placed: {median(waits) if waits else 'no placed referrals yet'}.",
                    False,
                ),
            ],
        ),
        "notes": [
            "The names of youth are never shown in these reports. Staff with access find them from the Referrals page."
        ],
    }


REPORTS = {
    "project-scorecard": {
        "title": "Project scorecard",
        "purpose": "How many youth were trained, referred and placed, by cohort and county.",
        "audience": "Directors, donors",
        "filters": ["period", "project", "cohort", "institution", "county", "gender"],
        "period_on": "when the youth's cohort started",
        "build": project_scorecard,
    },
    "placement-outcomes": {
        "title": "Placement outcomes",
        "purpose": "Who was placed, into what, with which employers and how fast.",
        "audience": "Directors, donors, management",
        "filters": ["period", "project", "cohort", "county", "sector", "pathway", "employer"],
        "period_on": "the placement start date",
        "build": placement_outcomes,
    },
    "equity-and-reach": {
        "title": "Equity and reach",
        "purpose": "Whether young women, younger and older youth and every county are reached and placed fairly.",
        "audience": "Donors, directors",
        "filters": ["period", "project", "cohort", "county"],
        "period_on": "when the youth's cohort started",
        "build": equity_and_reach,
    },
    "retention": {
        "title": "Retention after placement",
        "purpose": "Whether placed youth are still employed at each follow-up check-in.",
        "audience": "Donors, management",
        "filters": ["period", "project", "cohort", "county", "pathway", "checkin"],
        "period_on": "the placement start date",
        "build": retention,
    },
    "employer-pipeline": {
        "title": "Employer and pipeline health",
        "purpose": "Which employers are hiring, where referrals are stuck and which openings have no one put forward.",
        "audience": "Management, directors",
        "filters": ["period", "county", "sector", "employer", "stage"],
        "period_on": "the date a referral was submitted",
        "build": employer_pipeline,
    },
}


def index() -> list[dict]:
    return [{"slug": s, **{k: v for k, v in r.items() if k != "build"}} for s, r in REPORTS.items()]


def build(user, slug, params, *, today=None) -> dict | None:
    """One report for ``user`` with the filters in ``params``. ``None`` when the slug is unknown;
    raises ``FilterError`` for a filter value that cannot be used."""
    spec = REPORTS.get(slug)
    if spec is None:
        return None
    f = parse_filters(params)
    # Filters the report does not offer are ignored, not applied, so a shared link cannot mislead.
    for key in list(vars(f)):
        name = "period" if key in ("date_from", "date_to") else key
        if name not in spec["filters"]:
            setattr(f, key, None if key.startswith("date_") else "")
    today = today or date.today()
    ctx = Ctx(user, today)
    out = spec["build"](ctx, f)
    return {
        "slug": slug,
        "title": spec["title"],
        "purpose": spec["purpose"],
        "audience": spec["audience"],
        "period_on": spec["period_on"],
        "generated_on": today.isoformat(),
        "filters_applied": _applied(ctx, f, spec["filters"]),
        **out,
    }


def options(user) -> dict:
    """Every list the filter bar offers. Names and ids only."""
    o = participants.report_options()
    steps = sorted({s.offset_days for s in placements.followup_steps() if s.active})
    return {
        "projects": o["projects"],
        "cohorts": [
            {k: c[k] for k in ("id", "name", "project_id", "institution_id")} for c in o["cohorts"]
        ],
        "institutions": o["institutions"],
        "counties": o["counties"],
        "sectors": o["sectors"],
        "employers": [
            {"id": str(i), "name": n}
            for i, n in sorted(employers.employer_names().items(), key=lambda kv: kv[1].lower())
        ],
        "pathways": [{"id": c, "name": n} for c, n in PATHWAYS],
        "genders": [{"id": c, "name": n} for c, n in GENDERS],
        "stages": [{"id": c, "name": n} for c, n in STAGES],
        "checkins": [{"id": str(d), "name": _point_label(d)} for d in steps],
    }
