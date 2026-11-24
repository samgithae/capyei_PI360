/** What `/reporting/reports` sends. The shapes mirror `apps/reporting/reports.py`. */

export type FilterKey =
  | 'period'
  | 'project'
  | 'cohort'
  | 'institution'
  | 'county'
  | 'sector'
  | 'employer'
  | 'pathway'
  | 'gender'
  | 'stage'
  | 'checkin';

export interface ReportSummary {
  slug: string;
  title: string;
  purpose: string;
  audience: string;
  filters: FilterKey[];
  period_on: string;
}

export interface Option {
  id: string;
  name: string;
}

export interface FilterOptions {
  projects: Option[];
  cohorts: (Option & { project_id: string; institution_id: string })[];
  institutions: Option[];
  counties: Option[];
  sectors: Option[];
  employers: Option[];
  pathways: Option[];
  genders: Option[];
  stages: Option[];
  checkins: Option[];
}

export interface Tile {
  id: string;
  label: string;
  value: number | string | null;
  unit: string;
  hint: string;
}

export type ChartType = 'bar' | 'column' | 'pie' | 'line';

export interface Chart {
  id: string;
  title: string;
  type: ChartType;
  categories: string[];
  series: { name: string; values: number[] }[];
  unit: string;
  empty: string;
}

export type Cell = string | number | null;

export interface ReportTable {
  id: string;
  title: string;
  columns: string[];
  rows: Cell[][];
}

export interface Definition {
  name: string;
  meaning: string;
  approved: boolean;
}

export interface Report {
  slug: string;
  title: string;
  purpose: string;
  audience: string;
  period_on: string;
  generated_on: string;
  filters_applied: { key: string; label: string; value: string }[];
  tiles: Tile[];
  charts: Chart[];
  tables: ReportTable[];
  definitions: Definition[];
  notes: string[];
}

/** How each filter is drawn: its label, and which option list feeds it. */
export const FILTER_LABELS: Record<
  Exclude<FilterKey, 'period'>,
  { label: string; empty: string; options: keyof FilterOptions }
> = {
  project: {
    label: 'Project',
    empty: 'All projects',
    options: 'projects',
  },
  cohort: { label: 'Cohort', empty: 'All cohorts', options: 'cohorts' },
  institution: {
    label: 'Training institution',
    empty: 'All institutions',
    options: 'institutions',
  },
  county: { label: 'County', empty: 'All counties', options: 'counties' },
  sector: { label: 'Sector', empty: 'All sectors', options: 'sectors' },
  employer: {
    label: 'Employer',
    empty: 'All employers',
    options: 'employers',
  },
  pathway: { label: 'Pathway', empty: 'All pathways', options: 'pathways' },
  gender: { label: 'Gender', empty: 'All genders', options: 'genders' },
  stage: { label: 'Referral stage', empty: 'All stages', options: 'stages' },
  checkin: {
    label: 'Check-in point',
    empty: 'All check-in points',
    options: 'checkins',
  },
};

/** The query-string keys a report reads, in one place so the page, the fetch and the export agree. */
export const FILTER_PARAMS = [
  'from',
  'to',
  'project',
  'cohort',
  'institution',
  'county',
  'sector',
  'employer',
  'pathway',
  'gender',
  'stage',
  'checkin',
] as const;

export function filterQuery(
  search: URLSearchParams,
  extra: Record<string, string> = {},
): string {
  const q = new URLSearchParams(extra);
  for (const k of FILTER_PARAMS) {
    const v = search.get(k);
    if (v) q.set(k, v);
  }
  return q.toString();
}
