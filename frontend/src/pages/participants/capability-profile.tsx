import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BadgeCheck, Pencil } from 'lucide-react';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataCard } from '@/components/data-card';
import { ErrorState, LoadingState } from '@/components/states';
import {
  CapabilityFields,
  draftToPayload,
  LEVELS,
  type CapabilityDraft,
} from './capability-fields';

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
  grade: string;
  grade_id: string | null;
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
    grades: (Opt & { level_id: string; rank: number })[];
    skills: (Opt & { category: string })[];
    sectors: Opt[];
    work_patterns: Opt[];
  };
}

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
export function CapabilityProfile({
  id,
  self = false,
}: {
  id: string;
  /** A youth viewing their own record (portal): no verify buttons, and the profile is
   * read and saved through the youth endpoints. */
  self?: boolean;
}) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const key = ['participant-profile', self ? 'self' : id];
  const q = useQuery({
    queryKey: key,
    queryFn: () =>
      self
        ? api<{ profile: Profile }>('/youth/me').then((r) => r.profile)
        : api<Profile>(`/participants/${id}/profile`),
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

  const canEdit = self || can('participants.edit');
  const verifyBtn = (kind: string, f: Fact) =>
    !self && canEdit && f.id ? (
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
                    [x.grade, x.title, x.institution, x.year_awarded]
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
          self={self}
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

function ProfileEditor({
  id,
  self,
  profile,
  onClose,
  onSaved,
}: {
  id: string;
  self: boolean;
  profile: Profile;
  onClose: () => void;
  onSaved: (p: Profile) => void;
}) {
  const [draft, setDraft] = useState<CapabilityDraft>({
    quals: profile.qualifications.map((x) => ({
      id: x.id,
      level_id: x.level_id,
      title: x.title,
      institution: x.institution,
      grade_id: x.grade_id ?? '',
      year_awarded: x.year_awarded?.toString() ?? '',
    })),
    skills: profile.skills.map((x) => ({
      id: x.id,
      skill_id: x.skill_id,
      proficiency: String(x.proficiency),
    })),
    exp: profile.experience.map((x) => ({
      id: x.id,
      role_title: x.role_title,
      employer_name: x.employer_name,
      sector_id: x.sector_id ?? '',
      months: String(x.months),
    })),
    from: profile.readiness.available_from ?? '',
    patterns: profile.readiness.work_patterns,
    interests: profile.readiness.interest_sector_ids,
  });
  const [error, setError] = useState('');

  const save = useMutation({
    mutationFn: () =>
      api<Profile | { profile: Profile }>(
        self ? '/youth/profile' : `/participants/${id}/profile`,
        { method: 'PUT', body: JSON.stringify(draftToPayload(draft)) },
      ).then((r) => ('profile' in r ? r.profile : r)),
    onSuccess: onSaved,
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

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
          <CapabilityFields
            value={draft}
            onChange={setDraft}
            options={profile.options}
          />
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
