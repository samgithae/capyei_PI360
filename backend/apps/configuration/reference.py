"""Which reference kinds exist and which fields an administrator may write (T-057)."""

from dataclasses import dataclass, field

from . import models as m


@dataclass(frozen=True)
class Kind:
    model: type
    label: str
    fields: tuple = ()  # writable scalar fields besides code and name
    fks: dict = field(default_factory=dict)  # field name -> kind key of the parent
    named: bool = True  # has code and name
    creatable: bool = True


KINDS = {
    "sectors": Kind(m.Sector, "Sector"),
    "counties": Kind(m.County, "County", creatable=False),  # the 47 are seeded
    "sub-counties": Kind(m.SubCounty, "Sub-county", fks={"county": "counties"}),
    "wards": Kind(m.Ward, "Ward", fks={"sub_county": "sub-counties"}),
    "institutions": Kind(
        m.TrainingInstitution,
        "Training institution",
        fields=("kind",),
        fks={"county": "counties", "ward": "wards"},
    ),
    "programmes": Kind(m.Programme, "Programme", fields=("funder", "start", "end", "status")),
    "courses": Kind(
        m.Course,
        "Course",
        fields=("level",),
        fks={"programme": "programmes", "default_sector": "sectors"},
    ),
    "cohorts": Kind(
        m.Cohort,
        "Cohort",
        fields=("intake_year", "batch_no", "phase", "year_of_study", "start", "end", "status"),
        fks={"programme": "programmes", "institution": "institutions"},
    ),
    "cohort-courses": Kind(
        m.CohortCourse,
        "Cohort course",
        fields=("capacity",),
        fks={"cohort": "cohorts", "course": "courses"},
        named=False,
    ),
}
OPTIONAL_FKS = {"ward", "default_sector"}
