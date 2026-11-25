# ruff: noqa: E501
"""Public interface of apps.reporting (CMP-12, T-069/T-070).

The dashboard is built from named metrics. Each metric is a set of records (youth, referrals,
employers or opportunities), so the number on a tile and the list behind it can never disagree:
the count is the length of the same set the drill-down page lists. Every set is drawn from
what the signed-in user may see, so scope applies to counts and lists alike.

Working definitions live in ``METRICS`` and are shown in the app. Some still await CAP-YEI
approval; the dashboard says so rather than presenting them as settled."""

from collections import Counter
from datetime import date, datetime, timedelta
from statistics import median

from apps.api.access import has_permission
from apps.employers import services as employers
from apps.participants import services as participants
from apps.placements import services as placements
from apps.referrals import services as referrals

PERIODS = {"30": 30, "90": 90, "365": 365, "all": None}
CLOSING_SOON_DAYS = 14
AGE_BANDS = [
    ("under_18", "Under 18", 0, 17),
    ("18_24", "18 to 24", 18, 24),
    ("25_29", "25 to 29", 25, 29),
    ("30_plus", "30 and over", 30, 200),
]
GENDERS = [("female", "Female"), ("male", "Male"), ("other", "Other"), ("unknown", "Not recorded")]
PLACED_STAGES = {"placed"}

# What each number means. ``approved`` is False until CAP-YEI signs the definition off.
METRICS = [
    ("Registered youth", "Youth records you can see, excluding archived records and records merged into another.", False),
    ("Placed", "A youth with a placement recorded as placed, or a referral that reached the Placed stage. Counted once however many placements.", False),
    ("Placement rate", "Placed youth divided by registered youth.", False),
    ("Referred", "A youth with at least one submitted referral (a draft is not a referral).", True),
    ("Referral conversion", "Of referrals submitted in the period, the share that reached Placed.", False),
    ("Active employer", "An employer with status Active that is not archived.", False),
    ("Open opportunity", "An opportunity with status Open that is not archived.", False),
    ("Overdue referral", "A referral still in progress with no movement for the number of days set in Rules.", True),
    ("Time to placement", "Median days from submission to the Placed stage, for referrals placed in the period.", False),
]  # fmt: skip
NOT_CAPTURED = [
    "Retention at 30, 90 and 180 days (no follow-up records yet)",
    "Training completion (completion dates are not reliably imported)",
    "Disability, industry and skills demand (not collected)",
    "Predictive intelligence (needs approved rules and enough history)",
    "Staff productivity and project performance (planned next)",
]


def _age(f, today):
    if f["dob"]:
        d = f["dob"]
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    if f["age_at_source"] is not None:
        basis = f["age_basis"] or f["created_at"].date()
        return f["age_at_source"] + max(today.year - basis.year, 0)
    return None


def _band(age):
    for key, _label, lo, hi in AGE_BANDS:
        if age is not None and lo <= age <= hi:
            return key
    return "unknown"


def _stalled_days():
    from apps.intelligence import services as intelligence

    return intelligence.setting("support.stalled_days")


def outcomes(user, ids, refs, can_youth=True):
    """``(referred, placed, placement records)`` among the youth ``ids`` the user may see.
    Shared with the exports so a number in an export is the number on the dashboard."""
    referred = {r["participant_id"] for r in refs} & ids if can_youth else set()
    ref_placed = {
        r["participant_id"]
        for r in refs
        if r["stage"] in PLACED_STAGES or (r["stage"] == "closed" and r["placed_at"])
    }
    owners = participants.enrollment_owners(user) if can_youth else {}
    recs = [p for p in placements.placed_facts() if p["enrollment_id"] in owners]
    placed = (ref_placed & ids) | {owners[p["enrollment_id"]] for p in recs}
    return referred, placed, recs


def _universe(user, days, today) -> dict:
    """Every metric the user can see: ``{key: (kind, [ids])}`` plus supporting facts."""
    since = today - timedelta(days=days) if days else None
    sets: dict = {}
    facts: dict = {}
    can_youth = has_permission(user, "participants.view")
    can_ref = has_permission(user, "referrals.view")
    can_emp = has_permission(user, "employers.view")

    youth = participants.report_facts(user) if can_youth else []
    by_id = {y["id"]: y for y in youth}
    ids = set(by_id)
    sets["youth.registered"] = ("youth", sorted(ids, key=str))
    for g, _ in GENDERS:
        sets[f"youth.gender.{g}"] = ("youth", [y["id"] for y in youth if y["gender"] == g])
    for key, *_ in [*AGE_BANDS, ("unknown",)]:
        sets[f"youth.age.{key}"] = ("youth", [])
    for y in youth:
        sets[f"youth.age.{_band(_age(y, today))}"][1].append(y["id"])
    counties = {}
    for y in youth:
        k = str(y["county_id"]) if y["county_id"] else "none"
        counties[k] = y["county"] or "County not recorded"
        sets.setdefault(f"youth.county.{k}", ("youth", []))[1].append(y["id"])

    refs = referrals.report_facts(user) if can_ref else []
    referred, placed, recs = outcomes(user, ids, refs, can_youth)
    sets["youth.referred"] = ("youth", sorted(referred, key=str))
    sets["youth.not_referred"] = ("youth", sorted(ids - referred, key=str))
    sets["youth.placed"] = ("youth", sorted(placed, key=str))
    for g, _ in GENDERS:
        sets[f"youth.placed.gender.{g}"] = (
            "youth",
            [i for i in placed if by_id[i]["gender"] == g],
        )
    for k in counties:
        sets[f"youth.placed.county.{k}"] = (
            "youth",
            [i for i in placed if (str(by_id[i]["county_id"]) if by_id[i]["county_id"] else "none") == k],
        )  # fmt: skip

    now = datetime.now().astimezone()
    in_period = [r for r in refs if since is None or (r["referred_at"] and r["referred_at"].date() >= since)]  # fmt: skip
    sets["referrals.submitted"] = ("referral", [r["id"] for r in in_period])
    sets["referrals.submitted_placed"] = (
        "referral",
        [r["id"] for r in in_period if r["placed_at"]],
    )
    for stage in ("submitted", "under_review", "interview", "selected", "placed", "rejected", "withdrawn", "no_response", "closed"):  # fmt: skip
        sets[f"referrals.stage.{stage}"] = ("referral", [r["id"] for r in refs if r["stage"] == stage])  # fmt: skip
    in_progress = {"submitted", "under_review", "interview", "selected"}
    sets["referrals.active"] = ("referral", [r["id"] for r in refs if r["stage"] in in_progress])
    stalled = _stalled_days() if can_ref else 0
    cutoff = now - timedelta(days=stalled)
    sets["referrals.overdue"] = (
        "referral",
        [r["id"] for r in refs if r["stage"] in in_progress and r["updated_at"] <= cutoff],
    )

    emp = employers.report_facts() if can_emp else {"employers": [], "opportunities": []}
    opps = emp["opportunities"]
    open_opps = [o for o in opps if o["status"] == "open"]
    referred_opps = {r["opportunity_id"] for r in refs}
    soon = today + timedelta(days=CLOSING_SOON_DAYS)
    sets["employers.active"] = ("employer", [e["id"] for e in emp["employers"]])
    sets["opportunities.open"] = ("opportunity", [o["id"] for o in open_opps])
    sets["opportunities.closing_soon"] = (
        "opportunity",
        [o["id"] for o in open_opps if o["closing"] and today <= o["closing"] <= soon],
    )
    sets["opportunities.unreferred"] = (
        "opportunity",
        [o["id"] for o in open_opps if o["id"] not in referred_opps],
    )
    # An employer working in several counties counts once in each of them.
    emp_by_county = Counter(
        k for e in emp["employers"] for k in ([str(c) for c in e["county_ids"]] or ["none"])
    )

    facts.update(
        since=since,
        refs=refs,
        opps=opps,
        placed_recs=recs,
        counties=counties,
        emp_by_county=emp_by_county,
        stalled_days=stalled,
        can=(can_youth, can_ref, can_emp),
    )
    return {"sets": sets, "facts": facts}


def _n(sets, key):
    return len(sets[key][1]) if key in sets else 0


def _pct(a, b):
    return round(100 * a / b, 1) if b else None


def _month(d):
    return d.strftime("%Y-%m")


def _months(today, n=12):
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def _recent(u, n=5) -> dict:
    """The newest opportunities and the newest submitted referrals the user may see."""
    can_youth, can_ref, can_emp = u["facts"]["can"]
    out = {"opportunities": [], "referrals": []}
    if can_emp:
        newest = sorted(u["facts"]["opps"], key=lambda o: o["created_at"], reverse=True)[:n]
        info = employers.brief_opportunities([o["id"] for o in newest])
        out["opportunities"] = [
            {
                "id": str(o["id"]),
                "name": info[o["id"]]["name"],
                "detail": info[o["id"]]["detail"],
                "on": o["created_at"].isoformat(),
                "link": f"/opportunities/{o['id']}",
            }
            for o in newest
            if o["id"] in info
        ]
    if can_ref:
        newest = sorted(
            (r for r in u["facts"]["refs"] if r["referred_at"]),
            key=lambda r: r["referred_at"],
            reverse=True,
        )[:n]
        info = referrals.brief([r["id"] for r in newest])
        out["referrals"] = [
            {
                "id": str(r["id"]),
                "name": info[r["id"]]["name"],
                "detail": info[r["id"]]["detail"],
                "on": r["referred_at"].isoformat(),
                "link": f"/referrals/{r['id']}",
            }
            for r in newest
            if r["id"] in info
        ]
    return out


def _not_captured(user) -> list[str]:
    """The gaps list. Once disability is switched on for this user it is no longer a gap, so the
    line says only what is still missing (NEW-043)."""
    if not participants.flag_enabled("participants.disability", user):
        return NOT_CAPTURED
    return [
        "Industry and skills demand (not collected)" if line.startswith("Disability,") else line
        for line in NOT_CAPTURED
    ]


def dashboard(user, *, period="90", today=None) -> dict:
    today = today or date.today()
    days = PERIODS.get(period, 90)
    u = _universe(user, days, today)
    s, f = u["sets"], u["facts"]
    can_youth, can_ref, can_emp = f["can"]
    registered = _n(s, "youth.registered")
    placed = _n(s, "youth.placed")
    submitted = _n(s, "referrals.submitted")
    converted = _n(s, "referrals.submitted_placed")

    waits = [
        (r["placed_at"] - r["referred_at"]).days
        for r in f["refs"]
        if r["placed_at"]
        and r["referred_at"]
        and (f["since"] is None or r["placed_at"].date() >= f["since"])  # fmt: skip
    ]

    months = _months(today)
    ref, plc = Counter(), Counter()
    ref.update(_month(r["referred_at"]) for r in f["refs"] if r["referred_at"])
    plc.update(_month(r["placed_at"]) for r in f["refs"] if r["placed_at"])
    plc.update(_month(p["on"]) for p in f["placed_recs"] if p["on"])
    trend = [{"month": m, "referred": ref.get(m, 0), "placed": plc.get(m, 0)} for m in months]

    county_rows = []
    for k, name in f["counties"].items():
        n_reg = _n(s, f"youth.county.{k}")
        n_plc = _n(s, f"youth.placed.county.{k}")
        county_rows.append(
            {
                "key": k,
                "name": name,
                "registered": n_reg,
                "placed": n_plc,
                "rate": _pct(n_plc, n_reg),
                "employers": f["emp_by_county"].get(k, 0),
            }
        )
    county_rows.sort(key=lambda r: -r["registered"])

    alerts = []
    for key, label, hint in (
        (
            "referrals.overdue",
            "Referrals with no movement",
            f"in progress for {f['stalled_days']} days or more",
        ),  # fmt: skip
        (
            "opportunities.closing_soon",
            "Opportunities closing soon",
            f"within {CLOSING_SOON_DAYS} days",
        ),  # fmt: skip
        (
            "opportunities.unreferred",
            "Open opportunities with no referral",
            "no youth put forward yet",
        ),  # fmt: skip
        (
            "youth.not_referred",
            "Registered youth never referred",
            "not yet put forward for anything",
        ),  # fmt: skip
    ):
        if _n(s, key):
            alerts.append({"key": key, "label": label, "hint": hint, "count": _n(s, key)})

    return {
        "recent": _recent(u),
        "period": period if period in PERIODS else "90",
        "since": f["since"].isoformat() if f["since"] else None,
        "can": {"youth": can_youth, "referrals": can_ref, "employers": can_emp},
        "tiles": {
            "registered": registered,
            "placed": placed,
            "placement_rate": _pct(placed, registered),
            "referred": _n(s, "youth.referred"),
            "submitted": submitted,
            "conversion": _pct(converted, submitted),
            "active_employers": _n(s, "employers.active"),
            "open_opportunities": _n(s, "opportunities.open"),
            "median_days_to_placement": median(waits) if waits else None,
        },
        "funnel": [
            {"label": "Registered", "key": "youth.registered", "count": registered},
            {"label": "Referred", "key": "youth.referred", "count": _n(s, "youth.referred")},
            {"label": "Placed", "key": "youth.placed", "count": placed},
        ],
        "gender": [
            {
                "label": label,
                "key": f"youth.gender.{g}",
                "count": _n(s, f"youth.gender.{g}"),
                "placed_key": f"youth.placed.gender.{g}",
                "placed": _n(s, f"youth.placed.gender.{g}"),
                "rate": _pct(_n(s, f"youth.placed.gender.{g}"), _n(s, f"youth.gender.{g}")),
            }
            for g, label in GENDERS
            if _n(s, f"youth.gender.{g}")
        ],
        "age": [
            {"label": label, "key": f"youth.age.{k}", "count": _n(s, f"youth.age.{k}")}
            for k, label, *_ in [*AGE_BANDS, ("unknown", "Age not recorded")]
            if _n(s, f"youth.age.{k}")
        ],
        "pipeline": [
            {"label": label, "key": f"referrals.stage.{k}", "count": _n(s, f"referrals.stage.{k}")}
            for k, label in (
                ("submitted", "Submitted"),
                ("under_review", "Under review"),
                ("interview", "Interview"),
                ("selected", "Selected"),
                ("placed", "Placed"),
                ("rejected", "Rejected"),
                ("withdrawn", "Withdrawn"),
                ("no_response", "No response"),
            )
        ],
        "trend": trend,
        "counties": county_rows[:15],
        "alerts": alerts,
        "not_captured": _not_captured(user),
        "metrics": [{"name": n, "meaning": m, "approved": a} for n, m, a in METRICS],
    }


def drilldown(user, key, *, period="90", offset=0, size=25, today=None) -> dict | None:
    """The records behind one number, in pages. None when the key is not a metric."""
    today = today or date.today()
    u = _universe(user, PERIODS.get(period, 90), today)
    if key not in u["sets"]:
        return None
    kind, ids = u["sets"][key]
    brief = {
        "youth": participants.brief,
        "referral": referrals.brief,
        "employer": employers.brief_employers,
        "opportunity": employers.brief_opportunities,
    }[kind]
    link = {
        "youth": "/youth/",
        "referral": "/referrals/",
        "employer": "/employers/",
        "opportunity": "/opportunities/",
    }[kind]
    if kind == "youth":
        # Readers expect youth in name order, so names are fetched for the whole set.
        info = brief(ids)
        ordered = sorted(info, key=lambda i: (info[i]["name"].lower(), str(i)))
        page = ordered[offset : offset + size]
    else:
        page = sorted(ids, key=str)[offset : offset + size]
        info = brief(page)
    return {
        "key": key,
        "kind": kind,
        "total": len(ids),
        "offset": offset,
        "page_size": size,
        "results": [
            {
                "id": str(i),
                "name": info[i]["name"],
                "detail": info[i]["detail"],
                "link": f"{link}{i}",
            }
            for i in page
            if i in info
        ],
    }
