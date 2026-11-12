/** What the learner's journey API returns (apps/referrals/services.learner_journey). */
export interface JourneyItem {
  id: string;
  opportunity: string;
  employer: string;
  kind: string;
  location: string;
  stage: string;
  stage_label: string;
  ended: boolean;
  referred_at: string | null;
  updated_at: string;
  reached: string[];
  interview: { at: string; place: string; note: string } | null;
}
export interface Journey {
  steps: { key: string; label: string }[];
  counts: {
    referred: number;
    interview: number;
    selected: number;
    placed: number;
  };
  latest: JourneyItem | null;
  items: JourneyItem[];
}
export interface JourneyDetail extends JourneyItem {
  description: string;
  start_date: string | null;
  closing_date: string | null;
  timeline: { label: string; at: string }[];
}
export interface Notices {
  unread: number;
  items: { referral_id: string; text: string; at: string }[];
}
export interface MyPlacement {
  placements: {
    id: string;
    employer: string;
    designation: string;
    pathway: string;
    start_date: string | null;
  }[];
  referrals: {
    id: string;
    employer: string;
    designation: string;
    kind: string;
    location: string;
    start_date: string | null;
    placed_on: string | null;
  }[];
}
