/** Shapes the employer portal API returns (backend: apps/employer_portal). */

export interface Ref {
  id: string;
  name: string;
}

export interface Attention {
  kind: string;
  count: number;
  text: string;
  link: string;
}

export interface Activity {
  kind: string;
  at: string | null;
  text: string;
  link: string;
}

export interface Dashboard {
  can: { opportunities: boolean; referrals: boolean; team: boolean };
  attention: Attention[];
  activity: Activity[];
  opportunities?: {
    open: number;
    closing_soon: number;
    expired: number;
    awaiting: number;
    declined: number;
  };
  referrals?: {
    figures: {
      new: number;
      review: number;
      interviews: number;
      selected: number;
      placed_ytd: number;
      replied: number;
      waiting: number;
    };
    reply_days_median: number | null;
    reply_window_days: number;
    waiting_days: number;
    funnel: { stage: string; label: string; count: number }[];
    trend: { week: string; count: number }[];
    per_opportunity: {
      opportunity_id: string;
      opportunity: string;
      total: number;
      new: number;
    }[];
  };
}

export interface PublishRequest {
  state: 'none' | 'pending' | 'declined';
  requested_at: string | null;
  requested_by: string;
  declined_reason: string;
}

export interface OpportunityRow {
  id: string;
  title: string;
  kind: string;
  status: string;
  counties: Ref[];
  sectors: Ref[];
  positions: number;
  closing_date: string | null;
  publish_request: PublishRequest;
}

export interface OpportunityPage {
  total: number;
  page_size: number;
  results: OpportunityRow[];
}

export interface ReferralRow {
  id: string;
  candidate: string;
  opportunity_id: string;
  opportunity: string;
  stage: string;
  stage_label: string;
  referred_at: string;
  interview_at: string | null;
  updated_at: string;
  needs_action: boolean;
}

export interface ReferralPage {
  total: number;
  page_size: number;
  results: ReferralRow[];
}

export interface Member {
  id: string;
  /** The person's record on the contact list (one person, one record). */
  contact_id?: string | null;
  name: string;
  email: string;
  job_title: string;
  is_owner: boolean;
  state: 'active' | 'suspended' | 'expired' | 'pending';
  roles: string[];
  invited_at: string | null;
  expires_at: string | null;
  last_login: string | null;
}

export interface RoleOption {
  id: number;
  name: string;
  description: string;
}

export interface EmployerMe {
  employer: { id: string; name: string };
  member: { id: string; name: string; job_title: string; is_owner: boolean };
  roles: string[];
}

/** Opportunity statuses and referral views the dashboard links into. */
export const REFERRAL_VIEW_LABELS: Record<string, string> = {
  new: 'New, not yet looked at',
  review: 'Under review',
  interviews: 'Interviews',
  selected: 'Selected',
  placed_ytd: 'Placed this year',
  replied: 'Replied to',
  waiting: 'Waiting for your reply',
};

export const OPPORTUNITY_VIEW_LABELS: Record<string, string> = {
  open: 'Open',
  closing_soon: 'Closing soon',
  expired: 'Expired',
  awaiting: 'Awaiting PI 360 approval',
  declined: 'Sent back',
};
