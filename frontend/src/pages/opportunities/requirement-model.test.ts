import { describe, expect, it } from 'vitest';
import {
  BLANK,
  categoryLabel,
  problem,
  summary,
  toDraft,
  toPayload,
  type Lookup,
} from './requirement-model';

const lookup: Lookup = {
  levels: [{ id: 'l5', name: 'Diploma' }],
  skills: [{ id: 's1', name: 'Customer service' }],
  patterns: [{ id: 'full_time', name: 'Full time' }],
};

describe('requirement model', () => {
  it('maps a qualification onto the structured level and keeps the grade as a note', () => {
    const p = toPayload(
      {
        ...BLANK,
        category: 'qualification',
        item: 'l5',
        mandatory: true,
        note: 'C Plain',
      },
      lookup,
    );
    expect(p).toMatchObject({
      factor: 'qualification',
      qualification_level_id: 'l5',
      skill_id: null,
      is_mandatory: true,
      description: 'Diploma or higher — C Plain',
    });
  });

  it('treats competency as a skill and converts years to months', () => {
    expect(
      toPayload({ ...BLANK, category: 'competency', item: 's1' }, lookup),
    ).toMatchObject({ factor: 'skill', skill_id: 's1' });
    expect(
      toPayload(
        { ...BLANK, category: 'experience', duration: '2', unit: 'years' },
        lookup,
      ),
    ).toMatchObject({ factor: 'experience', min_months: 24 });
  });

  it('records certification and interest without a checked factor', () => {
    const p = toPayload(
      { ...BLANK, category: 'certification', item: 'Food hygiene' },
      lookup,
    );
    expect(p).toMatchObject({ factor: 'other', min_months: null });
    expect(categoryLabel({ ...p, id: 'x' })).toBe('Certification / Training');
  });

  it('round-trips an edit and reads old requirements', () => {
    const p = toPayload(
      { ...BLANK, category: 'experience', item: 'Kitchen', duration: '18' },
      lookup,
    );
    expect(toDraft(p)).toMatchObject({
      category: 'experience',
      item: 'Kitchen',
      duration: '18',
      unit: 'months',
    });
    const old = {
      factor: 'location',
      description: 'Within Kwale',
      is_mandatory: false,
      qualification_level_id: null,
      skill_id: null,
      min_months: null,
      needed_by: null,
      work_pattern: '',
    };
    expect(categoryLabel(old)).toBe('Location');
    expect(summary(old, lookup).name).toBe('Within Kwale');
  });

  it('asks for the one missing answer', () => {
    expect(problem({ ...BLANK, category: 'skill' })).toBe('Choose the skill.');
    expect(problem({ ...BLANK, category: 'skill', item: 's1' })).toBe('');
  });
});
