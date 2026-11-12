import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BadgeCheck, Pencil, Plus, Trash2 } from 'lucide-react';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { DataCard } from '@/components/data-card';
import { SelectField } from '@/components/shared/select-field';
import { ErrorState, LoadingState } from '@/components/states';

interface Fact {
  id: string | null;
  source: 'staff' | 'youth' | 'import' | null;
  verified: boolean;
  verified_by: string;
}
interface Qualification extends Fact {
  level_id: string;
  level: string;
  title: string;
  institution: string;
  year_awarded: number | null;
}
interface SkillRow extends Fact {
  skill_id: string;
  skill: string;
  proficiency: number;
}
interface Experience extends Fact {
  role_title: string;
  employer_name: string;
  sector_id: string | null;
  sector: string;
  months: number;
}
interface Readiness extends Fact {
  available_from: string | null;
  work_patterns: string[];
  interest_sector_ids: string[];
  interest_sectors: string[];
}
interface Opt {
  id: string;
  name: string;
}
interface Profile {
  qualifications: Qualification[];
  skills: SkillRow[];
  experience: Experience[];
  readiness: Readiness;
  summary: {
    highest_qualification: string;
    experience_months: number;
    skills: string[];
  };
  options: {
    levels: Opt[];
    skills: (Opt & { category: string })[];
    sectors: Opt[];
    work_patterns: Opt[];
  };
}

const LEVELS = [
  { id: '1', name: 'Basic' },
  { id: '2', name: 'Working' },
  { id: '3', name: 'Advanced' },
];

function Source({ fact }: { fact: Fact }) {
  if (fact.verified)
    return (
      <Badge variant="success" appearance="light" size="sm">
        <BadgeCheck className="size-3" /> Verified
      </Badge>
    );
  const label =
    fact.source === 'youth'
      ? 'Self-reported'
      : fact.source === 'import'
        ? 'Imported, not verified'
        : 'Not verified';
  return (
    <Badge variant="secondary" appearance="light" size="sm">
      {label}
    </Badge>
  );
}

function months(n: number) {
  const y = Math.floor(n / 12);
  const m = n % 12;
  return (
    [y ? `${y} yr` : '', m ? `${m} mo` : ''].filter(Boolean).join(' ') || '0 mo'
  );
}

/** Skills, qualifications, experience and availability of one youth, with who entered each and whether staff verified it. */
export function CapabilityProfile({ id }: { id: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const key = ['participant-profile', id];
  const q = useQuery({
    queryKey: key,
    queryFn: () => api<Profile>(`/participants/${id}/profile`),
    retry: false,
  });
  const verify = useMutation({
    mutationFn: (v: { kind: string; id: string; verified: boolean }) =>
      post(`/participants/${id}/profile/verify`, v),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });

  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  if (!p) return <LoadingState />;

  const canEdit = can('participants.edit');
  const verifyBtn = (kind: string, f: Fact) =>
    canEdit && f.id ? (
      <Button
        size="sm"
        variant="ghost"
        disabled={verify.isPending}
        onClick={() =>
          verify.mutate({ kind, id: f.id!, verified: !f.verified })
        }
      >
        {f.verified ? 'Unverify' : 'Verify'}
      </Button>
    ) : null;
  const row = (kind: string, f: Fact, text: string, extra?: string) => (
    <li key={f.id} className="flex flex-wrap items-center gap-2">
      <span>{text}</span>
      {extra && <span className="text-muted-foreground">{extra}</span>}
      <Source fact={f} />
      {verifyBtn(kind, f)}
    </li>
  );
  const r = p.readiness;
  const empty =
    !p.qualifications.length &&
    !p.skills.length &&
    !p.experience.length &&
    !r.id;

  return (
    <DataCard
      title="Skills and readiness"
      toolbar={
        canEdit && (
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            <Pencil /> {empty ? 'Add details' : 'Edit'}
          </Button>
        )
      }
    >
      <div className="space-y-4 p-5 text-sm">
        {empty ? (
          <p className="text-muted-foreground">
            Nothing recorded yet. Without these details the system cannot say
            whether this youth fits an opportunity; it will show them as
            &quot;not enough information&quot;.
          </p>
        ) : (
          <>
            <section>
              <h4 className="mb-1 font-medium">Qualifications</h4>
              <ul className="space-y-1">
                {p.qualifications.map((x) =>
                  row(
                    'qualification',
                    x,
                    x.level,
                    [x.title, x.institution, x.year_awarded]
                      .filter(Boolean)
                      .join(', '),
                  ),
                )}
              </ul>
              {!p.qualifications.length && (
                <p className="text-muted-foreground">None recorded.</p>
              )}
            </section>
            <section>
              <h4 className="mb-1 font-medium">Skills</h4>
              <ul className="space-y-1">
                {p.skills.map((x) =>
                  row(
                    'skill',
                    x,
                    x.skill,
                    LEVELS.find((l) => l.id === String(x.proficiency))?.name,
                  ),
                )}
              </ul>
              {!p.skills.length && (
                <p className="text-muted-foreground">None recorded.</p>
              )}
            </section>
            <section>
              <h4 className="mb-1 font-medium">
                Experience ({months(p.summary.experience_months)} in total)
              </h4>
              <ul className="space-y-1">
                {p.experience.map((x) =>
                  row(
                    'experience',
                    x,
                    x.role_title,
                    [x.employer_name, x.sector, months(x.months)]
                      .filter(Boolean)
                      .join(', '),
                  ),
                )}
              </ul>
              {!p.experience.length && (
                <p className="text-muted-foreground">None recorded.</p>
              )}
            </section>
            <section>
              <h4 className="mb-1 font-medium">Availability</h4>
              {r.id ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span>
                    {r.available_from
                      ? `Available from ${r.available_from}`
                      : 'Start date not given'}
                    {r.work_patterns.length > 0 &&
                      `; ${r.work_patterns
                        .map(
                          (c) =>
                            p.options.work_patterns.find((w) => w.id === c)
                              ?.name ?? c,
                        )
                        .join(', ')}`}
                    {r.interest_sectors.length > 0 &&
                      `; interested in ${r.interest_sectors.join(', ')}`}
                  </span>
                  <Source fact={r} />
                  {verifyBtn('readiness', r)}
                </div>
              ) : (
                <p className="text-muted-foreground">None recorded.</p>
              )}
            </section>
          </>
        )}
      </div>
      {editing && (
        <ProfileEditor
          id={id}
          profile={p}
          onClose={() => setEditing(false)}
          onSaved={(next) => {
            qc.setQueryData(key, next);
            setEditing(false);
          }}
        />
      )}
    </DataCard>
  );
}

interface QualDraft {
  id?: string | null;
  level_id: string;
  title: string;
  institution: string;
  year_awarded: string;
}
interface SkillDraft {
  id?: string | null;
  skill_id: string;
  proficiency: string;
}
interface ExpDraft {
  id?: string | null;
  role_title: string;
  employer_name: string;
  sector_id: string;
  months: string;
}

function ProfileEditor({
  id,
  profile,
  onClose,
  onSaved,
}: {
  id: string;
  profile: Profile;
  onClose: () => void;
  onSaved: (p: Profile) => void;
}) {
  const o = profile.options;
  const [quals, setQuals] = useState<QualDraft[]>(
    profile.qualifications.map((x) => ({
      id: x.id,
      level_id: x.level_id,
      title: x.title,
      institution: x.institution,
      year_awarded: x.year_awarded?.toString() ?? '',
    })),
  );
  const [skills, setSkills] = useState<SkillDraft[]>(
    profile.skills.map((x) => ({
      id: x.id,
      skill_id: x.skill_id,
      proficiency: String(x.proficiency),
    })),
  );
  const [exp, setExp] = useState<ExpDraft[]>(
    profile.experience.map((x) => ({
      id: x.id,
      role_title: x.role_title,
      employer_name: x.employer_name,
      sector_id: x.sector_id ?? '',
      months: String(x.months),
    })),
  );
  const [from, setFrom] = useState(profile.readiness.available_from ?? '');
  const [patterns, setPatterns] = useState(profile.readiness.work_patterns);
  const [interests, setInterests] = useState(
    profile.readiness.interest_sector_ids,
  );
  const [error, setError] = useState('');

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

  const save = useMutation({
    mutationFn: () =>
      api<Profile>(`/participants/${id}/profile`, {
        method: 'PUT',
        body: JSON.stringify({
          qualifications: quals.map((x) => ({
            ...x,
            year_awarded: x.year_awarded ? Number(x.year_awarded) : null,
          })),
          skills: skills.map((x) => ({
            ...x,
            proficiency: Number(x.proficiency),
          })),
          experience: exp.map((x) => ({
            ...x,
            sector_id: x.sector_id || null,
            months: Number(x.months || 0),
          })),
          readiness: {
            available_from: from || null,
            work_patterns: patterns,
            interest_sector_ids: interests,
          },
        }),
      }),
    onSuccess: onSaved,
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  const heading = 'text-sm font-medium';
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Skills and readiness</DialogTitle>
          <DialogDescription>
            Only fill what you know. Anything left empty is shown as missing,
            never as a failure. Changing an entry removes its verification.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="max-h-[60vh] space-y-5 overflow-auto">
          <section className="space-y-2">
            <p className={heading}>Qualifications</p>
            {quals.map((x, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <SelectField
                  label="Level"
                  className="w-52"
                  value={x.level_id}
                  options={o.levels}
                  onChange={(v) => patch(quals, setQuals, i, { level_id: v })}
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
                  onChange={(v) =>
                    patch(skills, setSkills, i, { proficiency: v })
                  }
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
                    onCheckedChange={() =>
                      toggle(interests, setInterests, s.id)
                    }
                  />
                  {s.name}
                </label>
              ))}
            </div>
          </section>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={save.isPending}
            onClick={() => {
              setError('');
              save.mutate();
            }}
          >
            {save.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
