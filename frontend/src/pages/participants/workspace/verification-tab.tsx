import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BadgeCheck, ShieldAlert } from 'lucide-react';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { DataCard } from '@/components/data-card';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { LEVELS } from '../capability-fields';
import { Field } from '../cv/cv-fields';
import type { CvProfileData, Fact, Opt } from '../cv/cv-types';
import {
  entries,
  entryStatus,
  verificationCounts,
  type EntryStatus,
} from './readiness';
import { monthsText, shortDate } from './types';

const STATUS: Record<
  EntryStatus,
  {
    label: string;
    variant: 'success' | 'warning' | 'destructive' | 'secondary' | 'info';
  }
> = {
  verified: { label: 'Verified', variant: 'success' },
  pending: { label: 'Pending', variant: 'info' },
  rejected: { label: 'Rejected', variant: 'destructive' },
  needs_reassessment: { label: 'Needs reassessment', variant: 'warning' },
  unverified: { label: 'Not verified', variant: 'secondary' },
};
const SOURCE = { youth: 'Self-reported', import: 'Imported', staff: 'Staff' };

interface Row {
  kind: string;
  fact: Fact;
  title: string;
  detail: string;
}

function rowsOf(p: CvProfileData): { heading: string; rows: Row[] }[] {
  const j = (...a: (string | number | null | undefined)[]) =>
    a.filter(Boolean).join(', ');
  return [
    {
      heading: 'Qualifications',
      rows: p.qualifications.map((x) => ({
        kind: 'qualification',
        fact: x,
        title: x.title || x.level,
        detail: j(x.level, x.institution, x.grade, x.year_awarded),
      })),
    },
    {
      heading: 'Skills',
      rows: p.skills.map((x) => ({
        kind: 'skill',
        fact: x,
        title: x.skill,
        detail: LEVELS.find((l) => l.id === String(x.proficiency))?.name ?? '',
      })),
    },
    {
      heading: 'Work experience',
      rows: p.experience.map((x) => ({
        kind: 'experience',
        fact: x,
        title: x.role_title,
        detail: j(x.employer_name, x.sector, monthsText(x.months)),
      })),
    },
    {
      heading: 'Certifications',
      rows: p.certifications.map((x) => ({
        kind: 'certification',
        fact: x,
        title: x.name,
        detail: j(x.issuer, x.year_obtained),
      })),
    },
    {
      heading: 'Practical experience',
      rows: p.practical.map((x) => ({
        kind: 'practical',
        fact: x,
        title: x.role || x.organisation,
        detail: j(x.organisation, x.kind),
      })),
    },
    {
      heading: 'Languages',
      rows: p.languages.map((x) => ({
        kind: 'language',
        fact: x,
        title: x.language,
        detail: x.proficiency,
      })),
    },
  ];
}

function ReviewDialog({
  id,
  row,
  methods,
  statuses,
  onClose,
}: {
  id: string;
  row: Row;
  methods: Opt[];
  statuses: Opt[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const v = row.fact.verification;
  const [status, setStatus] = useState(v?.status ?? 'verified');
  const [method, setMethod] = useState(v?.method ?? '');
  const [notes, setNotes] = useState(v?.notes ?? '');
  const save = useMutation({
    mutationFn: () =>
      post(`/participants/${id}/verification`, {
        kind: row.kind,
        id: row.fact.id,
        status,
        method: status === 'needs_reassessment' ? '' : method,
        notes,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['participant-profile', id] });
      void qc.invalidateQueries({ queryKey: ['participant-activity', id] });
      onClose();
    },
  });
  return (
    <FormModal
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Review: ${row.title}`}
      description="Record how this entry was checked. Only “Verified” counts as checked for matching."
      pending={save.isPending}
      error={
        save.isError
          ? save.error instanceof ApiError
            ? save.error.message
            : 'Could not save. Try again.'
          : ''
      }
      onSubmit={() => save.mutate()}
    >
      <div className="space-y-3">
        <SelectField
          label="Outcome"
          value={status}
          options={statuses}
          onChange={(s) => setStatus(s as typeof status)}
        />
        {status === 'verified' && (
          <SelectField
            label="How was it checked?"
            value={method}
            options={methods}
            emptyLabel="Choose a method"
            onChange={setMethod}
          />
        )}
        <Field
          label="Note (staff only)"
          hint="Not shown on the CV or to the youth or employers."
        >
          {(fid) => (
            <Textarea
              id={fid}
              rows={3}
              maxLength={1000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          )}
        </Field>
      </div>
    </FormModal>
  );
}

/** Every entry on the CV with who recorded it and where it stands with staff checks. */
export function VerificationTab({ id }: { id: string }) {
  const { can } = useAuth();
  const [reviewing, setReviewing] = useState<Row | null>(null);
  const q = useQuery({
    queryKey: ['participant-profile', id],
    queryFn: () => api<CvProfileData>(`/participants/${id}/profile`),
    retry: false,
  });
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const p = q.data;
  const canEdit = can('participants.edit');
  const counts = verificationCounts(p);
  if (entries(p).length === 0)
    return (
      <EmptyState
        title="Nothing to verify yet"
        hint="Add skills, education or experience on the CV tab first. Until then the system shows this youth as “not enough information”."
      />
    );
  return (
    <div className="space-y-5">
      <DataCard title="Verification summary">
        <div className="flex flex-wrap gap-2 p-5 text-sm">
          <Badge variant="success" appearance="light">
            <BadgeCheck className="size-3" /> {counts.verified} of{' '}
            {counts.total} verified
          </Badge>
          {counts.needs_reassessment > 0 && (
            <Badge variant="warning" appearance="light">
              <ShieldAlert className="size-3" /> {counts.needs_reassessment}{' '}
              changed since checked
            </Badge>
          )}
          {counts.pending > 0 && (
            <Badge variant="info" appearance="light">
              {counts.pending} pending
            </Badge>
          )}
          {counts.rejected > 0 && (
            <Badge variant="destructive" appearance="light">
              {counts.rejected} rejected
            </Badge>
          )}
          <Badge variant="secondary" appearance="light">
            {counts.unverified} not yet checked
          </Badge>
        </div>
      </DataCard>

      {rowsOf(p)
        .filter((g) => g.rows.length > 0)
        .map((g) => (
          <DataCard key={g.heading} title={g.heading}>
            <ul className="divide-y divide-border text-sm">
              {g.rows.map((r) => {
                const st = entryStatus(r.fact);
                const v = r.fact.verification;
                return (
                  <li
                    key={r.fact.id}
                    className="flex flex-wrap items-start justify-between gap-3 p-4"
                  >
                    <div className="min-w-0 space-y-1">
                      <p className="font-medium break-words">{r.title}</p>
                      {r.detail && (
                        <p className="break-words text-muted-foreground">
                          {r.detail}
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge
                          variant={STATUS[st].variant}
                          appearance="light"
                          size="sm"
                        >
                          {STATUS[st].label}
                        </Badge>
                        {r.fact.source && (
                          <span className="text-xs text-muted-foreground">
                            {SOURCE[r.fact.source]}
                          </span>
                        )}
                        {(v?.decided_by || r.fact.verified_by) && (
                          <span className="text-xs text-muted-foreground">
                            by {v?.decided_by || r.fact.verified_by}
                            {shortDate(v?.decided_at ?? r.fact.verified_at)
                              ? ` on ${shortDate(v?.decided_at ?? r.fact.verified_at)}`
                              : ''}
                          </span>
                        )}
                        {v?.method && (
                          <span className="text-xs text-muted-foreground">
                            Method:{' '}
                            {p.options.verification_methods.find(
                              (m) => m.id === v.method,
                            )?.name ?? v.method}
                          </span>
                        )}
                      </div>
                      {v?.notes && (
                        <p className="text-xs break-words text-muted-foreground">
                          Note: {v.notes}
                        </p>
                      )}
                    </div>
                    {canEdit && r.fact.id && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setReviewing(r)}
                      >
                        {st === 'verified' ? 'Review again' : 'Review'}
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          </DataCard>
        ))}
      {reviewing && (
        <ReviewDialog
          key={reviewing.fact.id}
          id={id}
          row={reviewing}
          methods={p.options.verification_methods}
          statuses={p.options.verification_statuses}
          onClose={() => setReviewing(null)}
        />
      )}
    </div>
  );
}
