/**
 * Friendly requirement categories mapped onto the structured requirement the matching engine
 * already reads (factor + typed value + mandatory flag). Nothing here decides a match: it only
 * translates what staff pick into the stored fields, and back again for display and editing.
 */

export type Category =
  | 'skill'
  | 'competency'
  | 'qualification'
  | 'experience'
  | 'certification'
  | 'interest'
  | 'working_condition'
  | 'other';

export interface Req {
  id?: string;
  factor: string;
  description: string;
  is_mandatory: boolean;
  qualification_level_id: string | null;
  min_grade_id?: string | null;
  skill_id: string | null;
  min_months: number | null;
  needed_by: string | null;
  work_pattern: string;
}

/** What the form holds: a few plain answers, never JSON or field paths. */
export interface Draft {
  category: Category;
  /** Catalogue id (skill / qualification) or free text (certification, interest, experience). */
  item: string;
  /** Lowest grade accepted for a qualification; empty means any grade. */
  minGrade: string;
  mandatory: boolean;
  note: string;
  duration: string;
  unit: 'months' | 'years';
  pattern: string;
  neededBy: string;
}

export const CATEGORIES: { id: Category; label: string; hint: string }[] = [
  {
    id: 'skill',
    label: 'Skill',
    hint: 'Checked against the skills on a youth profile.',
  },
  {
    id: 'competency',
    label: 'Competency',
    hint: 'Checked the same way as a skill.',
  },
  {
    id: 'qualification',
    label: 'Qualification',
    hint: 'Checked against the highest qualification recorded.',
  },
  {
    id: 'experience',
    label: 'Experience',
    hint: 'Checked against total months of experience.',
  },
  {
    id: 'certification',
    label: 'Certification / Training',
    hint: 'Recorded for staff to see; not checked automatically yet.',
  },
  {
    id: 'interest',
    label: 'Interest',
    hint: 'Recorded for staff to see; not checked automatically yet.',
  },
  {
    id: 'working_condition',
    label: 'Working condition',
    hint: 'Checked against availability and work pattern.',
  },
];

const SEP = ' — ';
const CERT = 'Certification / Training: ';
const INTEREST = 'Interest: ';

export const BLANK: Draft = {
  category: 'skill',
  item: '',
  minGrade: '',
  mandatory: false,
  note: '',
  duration: '',
  unit: 'months',
  pattern: '',
  neededBy: '',
};

export function categoryOf(r: Req): Category {
  if (r.factor === 'skill') return 'skill';
  if (r.factor === 'qualification') return 'qualification';
  if (r.factor === 'experience') return 'experience';
  if (r.factor === 'availability') return 'working_condition';
  if (r.description.startsWith(CERT)) return 'certification';
  if (r.description.startsWith(INTEREST)) return 'interest';
  return 'other';
}

export function categoryLabel(r: Req): string {
  if (r.factor === 'location') return 'Location';
  return CATEGORIES.find((c) => c.id === categoryOf(r))?.label ?? 'Other';
}

/** Splits the stored text into its name and the optional note after the separator. */
function split(text: string): { name: string; note: string } {
  const i = text.indexOf(SEP);
  return i < 0
    ? { name: text, note: '' }
    : { name: text.slice(0, i), note: text.slice(i + SEP.length) };
}

export function toDraft(r: Req): Draft {
  const cat = categoryOf(r);
  const { name, note } = split(r.description);
  const months = r.min_months ?? 0;
  const years = months > 0 && months % 12 === 0;
  const base = { ...BLANK, category: cat, mandatory: r.is_mandatory, note };
  switch (cat) {
    case 'skill':
      return { ...base, item: r.skill_id ?? '' };
    case 'qualification':
      return {
        ...base,
        item: r.qualification_level_id ?? '',
        minGrade: r.min_grade_id ?? '',
      };
    case 'experience':
      return {
        ...base,
        item: name === 'Work experience' ? '' : name,
        duration:
          r.min_months === null ? '' : String(years ? months / 12 : months),
        unit: years ? 'years' : 'months',
      };
    case 'certification':
      return { ...base, item: name.slice(CERT.length) };
    case 'interest':
      return { ...base, item: name.slice(INTEREST.length) };
    case 'working_condition':
      return {
        ...base,
        pattern: r.work_pattern,
        neededBy: r.needed_by ?? '',
        note: '',
      };
    default:
      return { ...base, item: r.description, note: '' };
  }
}

export interface Lookup {
  levels: { id: string; name: string }[];
  grades?: { id: string; name: string; level_id: string; rank: number }[];
  skills: { id: string; name: string }[];
  patterns: { id: string; name: string }[];
}

const withNote = (name: string, note: string) =>
  note.trim() ? `${name}${SEP}${note.trim()}` : name;

/** The one thing missing from the form, in plain words; empty when it can be saved. */
export function problem(d: Draft): string {
  switch (d.category) {
    case 'skill':
    case 'competency':
      return d.item ? '' : 'Choose the skill.';
    case 'qualification':
      return d.item ? '' : 'Choose the qualification.';
    case 'experience':
      return Number(d.duration) > 0
        ? ''
        : 'Say how long, for example 12 months.';
    case 'certification':
      return d.item.trim() ? '' : 'Enter the certification or training.';
    case 'interest':
      return d.item.trim() ? '' : 'Enter the interest.';
    case 'working_condition':
      return d.pattern || d.neededBy
        ? ''
        : 'Choose a work pattern or a start date.';
    default:
      return '';
  }
}

/** Builds the stored requirement. Only the typed value that belongs to the category is sent. */
export function toPayload(d: Draft, lookup: Lookup): Omit<Req, 'id'> {
  const base = {
    is_mandatory: d.mandatory,
    qualification_level_id: null,
    min_grade_id: null,
    skill_id: null,
    min_months: null,
    needed_by: null,
    work_pattern: '',
  };
  switch (d.category) {
    case 'skill':
    case 'competency': {
      const name = lookup.skills.find((s) => s.id === d.item)?.name ?? '';
      return {
        ...base,
        factor: 'skill',
        skill_id: d.item,
        description: withNote(name, d.note),
      };
    }
    case 'qualification': {
      const name = lookup.levels.find((s) => s.id === d.item)?.name ?? '';
      const grade = lookup.grades?.find(
        (g) => g.id === d.minGrade && g.level_id === d.item,
      );
      return {
        ...base,
        factor: 'qualification',
        qualification_level_id: d.item,
        min_grade_id: grade?.id ?? null,
        description: withNote(
          grade ? `${name}, grade ${grade.name} or above` : `${name} or higher`,
          d.note,
        ),
      };
    }
    case 'experience': {
      const n = Number(d.duration);
      return {
        ...base,
        factor: 'experience',
        min_months: d.unit === 'years' ? n * 12 : n,
        description: withNote(d.item.trim() || 'Work experience', d.note),
      };
    }
    case 'certification':
      return {
        ...base,
        factor: 'other',
        description: withNote(CERT + d.item.trim(), d.note),
      };
    case 'interest':
      return {
        ...base,
        factor: 'other',
        description: withNote(INTEREST + d.item.trim(), d.note),
      };
    case 'working_condition': {
      const name = lookup.patterns.find((p) => p.id === d.pattern)?.name;
      return {
        ...base,
        factor: 'availability',
        work_pattern: d.pattern,
        needed_by: d.neededBy || null,
        description: [name, d.neededBy && `start by ${d.neededBy}`]
          .filter(Boolean)
          .join(', '),
      };
    }
    default:
      return { ...base, factor: 'other', description: d.item };
  }
}

export function durationText(months: number): string {
  if (months > 0 && months % 12 === 0) {
    const y = months / 12;
    return `${y} year${y === 1 ? '' : 's'}`;
  }
  return `${months} month${months === 1 ? '' : 's'}`;
}

/** What to show in the list: the name, plus the extra criteria as short phrases. */
export function summary(
  r: Req,
  lookup: Lookup,
): { name: string; extras: string[] } {
  const cat = categoryOf(r);
  const { name, note } = split(r.description);
  const extras: string[] = [];
  let shown = name;
  if (cat === 'skill')
    shown = lookup.skills.find((s) => s.id === r.skill_id)?.name ?? name;
  if (cat === 'qualification') {
    const lvl = lookup.levels.find(
      (s) => s.id === r.qualification_level_id,
    )?.name;
    const g = lookup.grades?.find((x) => x.id === r.min_grade_id)?.name;
    shown = lvl
      ? g
        ? `${lvl}, grade ${g} or above`
        : `${lvl} or higher`
      : name;
  }
  if (cat === 'experience' && r.min_months !== null) {
    extras.push(`at least ${durationText(r.min_months)}`);
  }
  if (cat === 'certification') shown = name.slice(CERT.length);
  if (cat === 'interest') shown = name.slice(INTEREST.length);
  if (cat === 'working_condition') shown = r.description;
  if (note) extras.push(note);
  return { name: shown, extras };
}
