import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { SelectField } from '@/components/shared/select-field';

export interface CapOpt {
  id: string;
  name: string;
}
export interface CapabilityOptions {
  levels: CapOpt[];
  grades: (CapOpt & { level_id: string; rank: number })[];
  skills: (CapOpt & { category?: string })[];
  sectors: CapOpt[];
  work_patterns: CapOpt[];
}
export interface QualDraft {
  id?: string | null;
  level_id: string;
  title: string;
  institution: string;
  grade_id: string;
  year_awarded: string;
}
export interface SkillDraft {
  id?: string | null;
  skill_id: string;
  proficiency: string;
}
export interface ExpDraft {
  id?: string | null;
  role_title: string;
  employer_name: string;
  sector_id: string;
  months: string;
}
/** Everything the capability form edits, held by the parent so it can be saved or reviewed. */
export interface CapabilityDraft {
  quals: QualDraft[];
  skills: SkillDraft[];
  exp: ExpDraft[];
  from: string;
  patterns: string[];
  interests: string[];
}

export const emptyDraft = (): CapabilityDraft => ({
  quals: [],
  skills: [],
  exp: [],
  from: '',
  patterns: [],
  interests: [],
});

export const LEVELS = [
  { id: '1', name: 'Basic' },
  { id: '2', name: 'Working' },
  { id: '3', name: 'Advanced' },
];

/**
 * The API shape for a draft. With `skipBlank`, rows the user started but left
 * without their key field are dropped (the wizard), instead of being sent and rejected.
 */
export function draftToPayload(d: CapabilityDraft, skipBlank = false) {
  const q = skipBlank ? d.quals.filter((x) => x.level_id) : d.quals;
  const s = skipBlank ? d.skills.filter((x) => x.skill_id) : d.skills;
  const e = skipBlank ? d.exp.filter((x) => x.role_title.trim()) : d.exp;
  return {
    qualifications: q.map((x) => ({
      ...x,
      grade_id: x.grade_id || null,
      year_awarded: x.year_awarded ? Number(x.year_awarded) : null,
    })),
    skills: s.map((x) => ({ ...x, proficiency: Number(x.proficiency) })),
    experience: e.map((x) => ({
      ...x,
      sector_id: x.sector_id || null,
      months: Number(x.months || 0),
    })),
    readiness: {
      available_from: d.from || null,
      work_patterns: d.patterns,
      interest_sector_ids: d.interests,
    },
  };
}

/** True when the user entered anything worth saving. */
export function hasCapability(d: CapabilityDraft) {
  const p = draftToPayload(d, true);
  return (
    p.qualifications.length > 0 ||
    p.skills.length > 0 ||
    p.experience.length > 0 ||
    !!d.from ||
    d.patterns.length > 0 ||
    d.interests.length > 0
  );
}

const patch = <T,>(
  list: T[],
  set: (l: T[]) => void,
  i: number,
  v: Partial<T>,
) => set(list.map((x, j) => (j === i ? { ...x, ...v } : x)));
const drop = <T,>(list: T[], set: (l: T[]) => void, i: number) =>
  set(list.filter((_, j) => j !== i));
const toggle = (list: string[], set: (l: string[]) => void, v: string) =>
  set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

/** The qualification, skill, experience and availability inputs, controlled by the parent. */
export function CapabilityFields({
  value,
  onChange,
  options: o,
}: {
  value: CapabilityDraft;
  onChange: (d: CapabilityDraft) => void;
  options: CapabilityOptions;
}) {
  const { quals, skills, exp, from, patterns, interests } = value;
  const setQuals = (quals: QualDraft[]) => onChange({ ...value, quals });
  const setSkills = (skills: SkillDraft[]) => onChange({ ...value, skills });
  const setExp = (exp: ExpDraft[]) => onChange({ ...value, exp });
  const setFrom = (from: string) => onChange({ ...value, from });
  const setPatterns = (patterns: string[]) => onChange({ ...value, patterns });
  const setInterests = (interests: string[]) =>
    onChange({ ...value, interests });
  const heading = 'text-sm font-medium';
  return (
    <>
      <section className="space-y-2">
        <p className={heading}>Qualifications</p>
        {quals.map((x, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <SelectField
              label="Level"
              className="w-52"
              value={x.level_id}
              options={o.levels}
              onChange={(v) =>
                patch(quals, setQuals, i, { level_id: v, grade_id: '' })
              }
            />
            <Input
              className="w-48"
              aria-label="Title"
              placeholder="Title (optional)"
              value={x.title}
              onChange={(e) =>
                patch(quals, setQuals, i, { title: e.target.value })
              }
            />
            <Input
              className="w-44"
              aria-label="Institution"
              placeholder="Institution"
              value={x.institution}
              onChange={(e) =>
                patch(quals, setQuals, i, { institution: e.target.value })
              }
            />
            <SelectField
              label={x.level_id ? 'Grade' : 'Grade (pick a level first)'}
              className="w-52"
              value={x.grade_id}
              options={o.grades
                .filter((g) => g.level_id === x.level_id)
                .sort((p, q) => q.rank - p.rank)}
              emptyLabel="No grade recorded"
              disabled={!o.grades.some((g) => g.level_id === x.level_id)}
              onChange={(v) => patch(quals, setQuals, i, { grade_id: v })}
            />
            <Input
              className="w-24"
              aria-label="Year"
              inputMode="numeric"
              placeholder="Year"
              value={x.year_awarded}
              onChange={(e) =>
                patch(quals, setQuals, i, { year_awarded: e.target.value })
              }
            />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label="Remove qualification"
              onClick={() => drop(quals, setQuals, i)}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            setQuals([
              ...quals,
              {
                level_id: '',
                title: '',
                institution: '',
                grade_id: '',
                year_awarded: '',
              },
            ])
          }
        >
          <Plus /> Add qualification
        </Button>
      </section>

      <section className="space-y-2">
        <p className={heading}>Skills</p>
        {skills.map((x, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <SelectField
              label="Skill"
              className="w-64"
              value={x.skill_id}
              options={o.skills}
              onChange={(v) => patch(skills, setSkills, i, { skill_id: v })}
            />
            <SelectField
              label="Proficiency"
              className="w-36"
              value={x.proficiency}
              options={LEVELS}
              onChange={(v) => patch(skills, setSkills, i, { proficiency: v })}
            />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label="Remove skill"
              onClick={() => drop(skills, setSkills, i)}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            setSkills([...skills, { skill_id: '', proficiency: '2' }])
          }
        >
          <Plus /> Add skill
        </Button>
      </section>

      <section className="space-y-2">
        <p className={heading}>Work experience</p>
        {exp.map((x, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <Input
              className="w-44"
              aria-label="Role"
              placeholder="Role"
              value={x.role_title}
              onChange={(e) =>
                patch(exp, setExp, i, { role_title: e.target.value })
              }
            />
            <Input
              className="w-44"
              aria-label="Employer"
              placeholder="Employer"
              value={x.employer_name}
              onChange={(e) =>
                patch(exp, setExp, i, { employer_name: e.target.value })
              }
            />
            <SelectField
              label="Sector"
              className="w-40"
              emptyLabel="Sector"
              value={x.sector_id}
              options={o.sectors}
              onChange={(v) => patch(exp, setExp, i, { sector_id: v })}
            />
            <Input
              className="w-24"
              aria-label="Months"
              inputMode="numeric"
              placeholder="Months"
              value={x.months}
              onChange={(e) =>
                patch(exp, setExp, i, { months: e.target.value })
              }
            />
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label="Remove experience"
              onClick={() => drop(exp, setExp, i)}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            setExp([
              ...exp,
              {
                role_title: '',
                employer_name: '',
                sector_id: '',
                months: '',
              },
            ])
          }
        >
          <Plus /> Add experience
        </Button>
      </section>

      <section className="space-y-2">
        <p className={heading}>Availability</p>
        <div className="flex items-center gap-2 text-sm">
          <label htmlFor="avail-from">Available from</label>
          <Input
            id="avail-from"
            type="date"
            className="w-44"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          {o.work_patterns.map((w) => (
            <label key={w.id} className="flex items-center gap-2">
              <Checkbox
                checked={patterns.includes(w.id)}
                onCheckedChange={() => toggle(patterns, setPatterns, w.id)}
              />
              {w.name}
            </label>
          ))}
        </div>
        <p className="pt-1 text-sm text-muted-foreground">
          Sectors of interest
        </p>
        <div className="flex flex-wrap gap-4 text-sm">
          {o.sectors.map((s) => (
            <label key={s.id} className="flex items-center gap-2">
              <Checkbox
                checked={interests.includes(s.id)}
                onCheckedChange={() => toggle(interests, setInterests, s.id)}
              />
              {s.name}
            </label>
          ))}
        </div>
      </section>
    </>
  );
}
