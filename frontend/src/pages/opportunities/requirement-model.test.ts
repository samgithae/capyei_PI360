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
  levels: [
    { id: 'l2', name: 'Secondary' },
    { id: 'l5', name: 'Diploma' },
  ],
  grades: [
    { id: 'gb', name: 'B', level_id: 'l2', rank: 9 },
    { id: 'gc', name: 'C', level_id: 'l2', rank: 6 },
  ],
  skills: [{ id: 's1', name: 'Customer service' }],
  patterns: [{ id: 'full_time', name: 'Full time' }],
};

describe('requirement model', () => {
  it('maps a qualification onto the structured level and a note', () => {
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

  it('sends a minimum grade for the level and ignores one from another level', () => {
    const d = { ...BLANK, category: 'qualification' as const, item: 'l2' };
    const p = toPayload({ ...d, minGrade: 'gc' }, lookup);
    expect(p).toMatchObject({
      qualification_level_id: 'l2',
      min_grade_id: 'gc',
      description: 'Secondary, grade C or above',
    });
    expect(toDraft({ ...p, id: 'x' }).minGrade).toBe('gc');
    expect(summary(p, lookup).name).toBe('Secondary, grade C or above');
    const other = toPayload({ ...d, item: 'l5', minGrade: 'gc' }, lookup);
    expect(other.min_grade_id).toBeNull();
    expect(other.description).toBe('Diploma or higher');
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
