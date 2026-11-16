export interface Count {
  label: string;
  key: string;
  count: number;
}
export interface RecentRow {
  id: string;
  name: string;
  detail: string;
  on: string;
  link: string;
}
export interface Dashboard {
  recent: { opportunities: RecentRow[]; referrals: RecentRow[] };
  period: string;
  since: string | null;
  can: { youth: boolean; referrals: boolean; employers: boolean };
  tiles: {
    registered: number;
    placed: number;
    placement_rate: number | null;
    referred: number;
    submitted: number;
    conversion: number | null;
    active_employers: number;
    open_opportunities: number;
    median_days_to_placement: number | null;
  };
  funnel: Count[];
  gender: (Count & {
    placed_key: string;
    placed: number;
    rate: number | null;
  })[];
  age: Count[];
  pipeline: Count[];
  trend: { month: string; referred: number; placed: number }[];
  counties: {
    key: string;
    name: string;
    registered: number;
    placed: number;
    rate: number | null;
    employers: number;
  }[];
  alerts: { key: string; label: string; hint: string; count: number }[];
  not_captured: string[];
  metrics: { name: string; meaning: string; approved: boolean }[];
}
export interface DrillRow {
  id: string;
  name: string;
  detail: string;
  link: string;
}
export interface Drill {
  key: string;
  kind: string;
  total: number;
  offset: number;
  page_size: number;
  results: DrillRow[];
}
export const PERIODS = [
  { id: '30', name: 'Last 30 days' },
  { id: '90', name: 'Last 90 days' },
  { id: '365', name: 'Last 12 months' },
  { id: 'all', name: 'All time' },
];
/** The page that lists the records behind one dashboard number. */
export const listUrl = (key: string, title: string, period: string) =>
  `/dashboard/list?key=${encodeURIComponent(key)}&period=${period}&title=${encodeURIComponent(title)}`;
