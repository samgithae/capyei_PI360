import type { CvDoc, CvProfileData, Fact } from '../cv/cv-types';

// Three separate things, never blended into one score:
//   1. CV completeness   - what is missing from the CV (the server works it out).
//   2. Verification      - how many entries staff have checked.
//   3. Placement readiness - plain yes/no indicators read from data we really hold.

export type TabId =
  | 'overview'
  | 'cv'
  | 'history'
  | 'skills'
  | 'referrals'
  | 'account';

export type EntryStatus =
  | 'verified'
  | 'pending'
  | 'rejected'
  | 'needs_reassessment'
  | 'unverified';

export const entryStatus = (f: Fact): EntryStatus =>
  f.verification?.status ?? (f.verified ? 'verified' : 'unverified');

/** Every entry that staff can verify, in one list. */
export function entries(p: CvProfileData): Fact[] {
  return [
    ...p.qualifications,
    ...p.skills,
    ...p.experience,
    ...p.certifications,
    ...p.practical,
    ...p.languages,
  ];
}

export interface VerificationCounts {
  total: number;
  verified: number;
  pending: number;
  rejected: number;
  needs_reassessment: number;
  unverified: number;
}

export function verificationCounts(p: CvProfileData): VerificationCounts {
  const out: VerificationCounts = {
    total: 0,
    verified: 0,
    pending: 0,
    rejected: 0,
    needs_reassessment: 0,
    unverified: 0,
  };
  for (const f of entries(p)) {
    out.total += 1;
    out[entryStatus(f)] += 1;
  }
  return out;
}

export interface Indicator {
  key: string;
  label: string;
  done: boolean;
  hint: string;
  tab: TabId;
}

/** Actionable yes/no indicators. Not a score: each one says what is missing and where to fix it. */
export function placementIndicators(
  cv: CvDoc,
  p: CvProfileData,
  activeReferrals: number | null,
): Indicator[] {
  const r = p.readiness;
  const counts = verificationCounts(p);
  const list: Indicator[] = [
    {
      key: 'cv',
      label: 'CV essentials in place',
      done: cv.completeness.missing.length === 0,
      hint: cv.completeness.missing.map((m) => m.label).join(', '),
      tab: 'cv',
    },
    {
      key: 'availability',
      label: 'Availability date recorded',
      done: !!r.available_from,
      hint: 'Add when the youth can start work.',
      tab: 'cv',
    },
    {
      key: 'preferences',
      label: 'Job preferences recorded',
      done:
        r.preferred_roles.length > 0 ||
        r.interest_sectors.length > 0 ||
        r.preferred_counties.length > 0,
      hint: 'Add preferred roles, sectors or locations.',
      tab: 'cv',
    },
    {
      key: 'skills',
      label: 'Skills listed',
      done: p.skills.length > 0,
      hint: 'Add at least one skill.',
      tab: 'cv',
    },
    {
      key: 'background',
      label: 'Education or work history recorded',
      done:
        p.qualifications.length > 0 ||
        p.experience.length > 0 ||
        p.practical.length > 0 ||
        r.no_work_experience,
      hint: 'Add education, or tick "no work experience yet".',
      tab: 'history',
    },
    {
      key: 'verified',
      label: 'At least one entry verified by staff',
      done: counts.verified > 0,
      hint: 'Check an entry on the Skills & Verification tab.',
      tab: 'skills',
    },
  ];
  if (counts.needs_reassessment > 0)
    list.push({
      key: 'reassess',
      label: `${counts.needs_reassessment} entr${counts.needs_reassessment === 1 ? 'y' : 'ies'} changed since checked`,
      done: false,
      hint: 'Review them again.',
      tab: 'skills',
    });
  if (activeReferrals !== null)
    list.push({
      key: 'referral',
      label: 'Referred to an opportunity',
      done: activeReferrals > 0,
      hint: 'No active referral yet.',
      tab: 'referrals',
    });
  return list;
}

const OPEN = new Set([
  'draft',
  'submitted',
  'under_review',
  'interview',
  'selected',
]);
/** Referrals still in progress (not placed, closed, rejected, withdrawn or no response). */
export const isOpenStage = (stage: string) => OPEN.has(stage);
