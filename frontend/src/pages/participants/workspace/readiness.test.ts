import { describe, expect, it } from 'vitest';
import type { CvDoc, CvProfileData, Fact } from '../cv/cv-types';
import {
  entryStatus,
  isOpenStage,
  placementIndicators,
  verificationCounts,
} from './readiness';

const fact = (over: Partial<Fact> = {}): Fact => ({
  id: 'x',
  source: 'staff',
  verified: false,
  verified_by: '',
  ...over,
});
const profile = (over: Partial<CvProfileData> = {}): CvProfileData =>
  ({
    qualifications: [],
    skills: [],
    experience: [],
    certifications: [],
    practical: [],
    languages: [],
    readiness: {
      ...fact(),
      available_from: null,
      work_patterns: [],
      interest_sector_ids: [],
      interest_sectors: [],
      summary: '',
      preferred_roles: [],
      preferred_county_ids: [],
      preferred_counties: [],
      willing_to_relocate: null,
      no_work_experience: false,
    },
    options: {},
    ...over,
  }) as unknown as CvProfileData;
const cv = (missing: string[] = []) =>
  ({
    completeness: {
      percent: 50,
      suggestions: [],
      missing: missing.map((label) => ({ key: label, label, hint: '' })),
    },
  }) as unknown as CvDoc;
const skill = (over: Partial<Fact>) =>
  ({ ...fact(over), skill_id: 's', skill: 'Cooking', proficiency: 2 }) as never;

describe('entryStatus', () => {
  it('prefers the staff check record over the plain flag', () => {
    expect(
      entryStatus(
        fact({
          verified: false,
          verification: {
            status: 'needs_reassessment',
            method: '',
            notes: '',
            decided_by: '',
            decided_at: null,
          },
        }),
      ),
    ).toBe('needs_reassessment');
  });
  it('falls back to verified / unverified', () => {
    expect(entryStatus(fact({ verified: true }))).toBe('verified');
    expect(entryStatus(fact())).toBe('unverified');
  });
});

describe('verificationCounts', () => {
  it('counts each status separately', () => {
    const p = profile({
      skills: [skill({ verified: true }), skill({}), skill({})],
    });
    expect(verificationCounts(p)).toMatchObject({
      total: 3,
      verified: 1,
      unverified: 2,
    });
  });
});

describe('placementIndicators', () => {
  it('reports what is missing without inventing a score', () => {
    const list = placementIndicators(cv(['Summary']), profile(), null);
    expect(list.every((i) => !i.done)).toBe(true);
    expect(list.find((i) => i.key === 'cv')?.hint).toBe('Summary');
    expect(list.find((i) => i.key === 'referral')).toBeUndefined();
  });
  it('treats "no work experience yet" as background, not a gap', () => {
    const p = profile();
    p.readiness.no_work_experience = true;
    const list = placementIndicators(cv(), p, 0);
    expect(list.find((i) => i.key === 'background')?.done).toBe(true);
    expect(list.find((i) => i.key === 'referral')?.done).toBe(false);
  });
  it('flags entries that changed after being checked', () => {
    const changed = skill({
      verification: {
        status: 'needs_reassessment',
        method: '',
        notes: '',
        decided_by: '',
        decided_at: null,
      },
    });
    const list = placementIndicators(cv(), profile({ skills: [changed] }), 1);
    expect(list.find((i) => i.key === 'reassess')?.tab).toBe('skills');
    expect(list.find((i) => i.key === 'referral')?.done).toBe(true);
  });
});

describe('isOpenStage', () => {
  it('is false once a referral is finished', () => {
    expect(isOpenStage('interview')).toBe(true);
    expect(isOpenStage('placed')).toBe(false);
    expect(isOpenStage('rejected')).toBe(false);
  });
});
