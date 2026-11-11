import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { MoveRight, Undo2, UserCheck } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  ActivityTimeline,
  type AuditEvent,
} from '@/components/shared/activity-timeline';
import { DetailList, Section } from '@/components/shared/info-card';
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import {
  stageName,
  STAGES,
  UNSUCCESSFUL,
  useRefreshReferrals,
  type Reason,
  type ReferralDetail,
  type StageEvent,
} from './referral-shared';

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString() : '';

/** Button text for a normal move to `to`. */
const MOVE_LABEL: Record<string, string> = {
  submitted: 'Submit',
  under_review: 'Under review',
  interview: 'Interview',
  selected: 'Selected',
  placed: 'Placed',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  no_response: 'No response',
  closed: 'Close',
};

/** Reason picker for an unsuccessful outcome. The server filters reasons by stage. */
function ReasonField({
  stage,
  value,
  onChange,
}: {
  stage: string;
  value: string;
  onChange: (id: string, reason?: Reason) => void;
}) {
  const reasons = useQuery({
    queryKey: ['referral-reasons', stage],
    queryFn: () => api<Reason[]>(`/referrals/reasons?stage=${stage}`),
  });
  return (
    <div className="space-y-1.5">
      <Label>
        Reason <span className="text-destructive">*</span>
      </Label>
      <SelectField
        label="Choose a reason"
        value={value}
        options={reasons.data ?? []}
        onChange={(id) =>
          onChange(
            id,
            reasons.data?.find((r) => r.id === id),
          )
        }
      />
    </div>
  );
}

/** The referral's own history: each stage change, oldest first. Corrections are marked and
 * point at what they correct; nothing is ever removed. */
function StageHistory({ events }: { events: StageEvent[] }) {
  if (events.length === 0) return <EmptyState title="No stage changes yet" />;
  const corrected = new Set(events.map((e) => e.corrects).filter(Boolean));
  return (
    <ol className="relative space-y-5 border-s border-border ps-6">
      {events.map((e) => (
        <li key={e.id} className="relative">
          <span className="absolute -start-[2.2rem] flex size-6 items-center justify-center rounded-full border bg-background text-muted-foreground">
            {e.kind === 'correction' ? (
              <Undo2 className="size-3.5" />
            ) : (
              <MoveRight className="size-3.5" />
            )}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-foreground">
              {e.from ? `${stageName(e.from)} to ` : 'Created as '}
              {stageName(e.to)}
            </p>
            {e.kind === 'correction' && (
              <Badge variant="warning" appearance="light">
                Correction
              </Badge>
            )}
            {corrected.has(e.id) && (
              <Badge variant="secondary" appearance="light">
                Corrected later
              </Badge>
            )}
          </div>
          {e.reason && (
            <p className="text-xs text-muted-foreground">Reason: {e.reason}</p>
          )}
          {e.note && <p className="text-sm text-foreground">{e.note}</p>}
          <p className="text-xs text-muted-foreground">
            {e.actor} · {when(e.at)}
          </p>
        </li>
      ))}
    </ol>
  );
}

const BLANK = { to: '', reason: '', note: '', needsNote: false };

export function ReferralPage() {
  const { id } = useParams();
  const refresh = useRefreshReferrals();
  // One form state shared by the move and correction dialogs; `mode` says which is open.
  const [mode, setMode] = useState<'move' | 'correct' | null>(null);
  const [form, setForm] = useState(BLANK);
  const [assigning, setAssigning] = useState(false);
  const [assignee, setAssignee] = useState('');
  const [error, setError] = useState('');

  const q = useQuery({
    queryKey: ['referral', id],
    queryFn: () => api<ReferralDetail>(`/referrals/${id}`),
    retry: false,
  });
  const audit = useQuery({
    queryKey: ['referral-history', id],
    queryFn: () => api<AuditEvent[]>(`/referrals/${id}/history`),
  });
  const people = useQuery({
    queryKey: ['referral-assignees'],
    queryFn: () => api<{ id: number; name: string }[]>('/referrals/assignees'),
    enabled: assigning,
  });

  const done = (message: string) => {
    toast.success(message);
    setMode(null);
    setAssigning(false);
    setForm(BLANK);
    setError('');
    refresh();
  };
  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'Something went wrong.');

  const save = useMutation({
    mutationFn: () =>
      post(
        `/referrals/${id}/${mode === 'correct' ? 'correct' : 'transition'}`,
        {
          to: form.to,
          reason_id: form.reason || null,
          note: form.note,
        },
      ),
    onSuccess: () =>
      done(
        mode === 'correct'
          ? 'Stage corrected. The earlier entry stays in the history.'
          : `Referral moved to ${stageName(form.to)}.`,
      ),
    onError: fail,
  });
  const assign = useMutation({
    mutationFn: () =>
      post(`/referrals/${id}/assign`, { user_id: Number(assignee) }),
    onSuccess: () => done('Referral reassigned.'),
    onError: fail,
  });

  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Referral not found"
            hint="It may be outside your caseload, or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        <Link className="text-primary" to="/referrals">
          Back to referrals
        </Link>
      </div>
    );
  }
  const r = q.data;
  if (!r) return <LoadingState />;

  const closed = r.stage === 'closed';
  // Correcting a closed referral reopens it, which needs a manager (referrals.approve).
  const canCorrect = closed ? r.can.reopen : r.can.edit;
  const openMove = (to: string) => {
    setForm({ ...BLANK, to });
    setError('');
    setMode('move');
  };
  const openCorrect = () => {
    setForm(BLANK);
    setError('');
    setMode('correct');
  };
  const needsReason = UNSUCCESSFUL.includes(form.to);

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{`Referral: ${r.participant} | PI 360`}</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Referrals', to: '/referrals' },
          { label: r.participant },
        ]}
        title={`${r.participant} for ${r.opportunity}`}
        badges={<StatusBadge status={r.stage} label={r.stage_label} />}
        meta={
          <>
            <Link
              className="text-primary hover:underline"
              to={`/opportunities/${r.opportunity_id}`}
            >
              {r.opportunity}
            </Link>
            <span>{r.employer}</span>
            <span>Assigned to {r.assigned_to || 'nobody'}</span>
          </>
        }
        actions={
          <>
            {r.can.edit &&
              r.next_stages.map((to) => (
                <Button
                  key={to}
                  variant={UNSUCCESSFUL.includes(to) ? 'outline' : 'primary'}
                  onClick={() => openMove(to)}
                >
                  {MOVE_LABEL[to] ?? stageName(to)}
                </Button>
              ))}
            {canCorrect && (
              <Button variant="outline" onClick={openCorrect}>
                <Undo2 /> {closed ? 'Reopen' : 'Correct stage'}
              </Button>
            )}
            {r.can.reassign && (
              <Button
                variant="outline"
                onClick={() => {
                  setAssignee(r.assigned_to_id ? String(r.assigned_to_id) : '');
                  setError('');
                  setAssigning(true);
                }}
              >
                <UserCheck /> Reassign
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Section title="Overview">
            <DetailList
              items={[
                {
                  label: 'Stage',
                  value: <StatusBadge status={r.stage} label={r.stage_label} />,
                },
                {
                  label: 'Youth',
                  value: (
                    <Link
                      className="text-primary hover:underline"
                      to={`/youth/${r.participant_id}`}
                    >
                      {r.participant}
                    </Link>
                  ),
                },
                {
                  label: 'Opportunity',
                  value: (
                    <Link
                      className="text-primary hover:underline"
                      to={`/opportunities/${r.opportunity_id}`}
                    >
                      {r.opportunity}
                    </Link>
                  ),
                },
                { label: 'Employer', value: r.employer },
                { label: 'Reason', value: r.reason },
                { label: 'Reason note', value: r.reason_note },
                {
                  label: 'Origin',
                  value:
                    r.origin === 'trainee'
                      ? 'Trainee application'
                      : 'Staff referral',
                },
                { label: 'Created by', value: r.created_by },
                { label: 'Referred', value: when(r.referred_at) },
                { label: 'Closed', value: when(r.closed_at) },
              ]}
            />
          </Section>
          <Section
            title="Stage history"
            description="Every move is kept. A correction adds a new entry; it never rewrites an old one."
          >
            <StageHistory events={r.history} />
          </Section>
        </div>
        <Section title="Activity">
          {audit.isPending ? (
            <LoadingState rows={3} />
          ) : (
            <ActivityTimeline events={audit.data ?? []} />
          )}
        </Section>
      </div>

      <FormModal
        open={mode !== null}
        onOpenChange={(o) => !o && setMode(null)}
        title={
          mode === 'correct'
            ? closed
              ? 'Reopen referral'
              : 'Correct the stage'
            : `Move to ${stageName(form.to)}`
        }
        description={
          mode === 'correct'
            ? 'Use this when a stage was recorded by mistake. The wrong entry stays in the history, marked as corrected.'
            : needsReason
              ? 'An unsuccessful outcome needs a reason.'
              : undefined
        }
        submitLabel={mode === 'correct' ? 'Save correction' : 'Move'}
        pending={save.isPending}
        error={error}
        onSubmit={() => {
          if (!form.to) return setError('Choose the correct stage.');
          if (needsReason && !form.reason) return setError('Choose a reason.');
          if ((mode === 'correct' || form.needsNote) && !form.note.trim())
            return setError('Add a note saying what happened.');
          save.mutate();
        }}
      >
        {mode === 'correct' && (
          <div className="space-y-1.5">
            <Label>
              Correct stage <span className="text-destructive">*</span>
            </Label>
            <SelectField
              label="Choose the stage it should be at"
              value={form.to}
              options={STAGES.filter(
                (s) => s.id !== r.stage && s.id !== 'closed',
              )}
              onChange={(to) => setForm({ ...form, to, reason: '' })}
            />
          </div>
        )}
        {needsReason && (
          <ReasonField
            key={form.to}
            stage={form.to}
            value={form.reason}
            onChange={(reason, picked) =>
              setForm({ ...form, reason, needsNote: !!picked?.needs_note })
            }
          />
        )}
        <div className="space-y-1.5">
          <Label htmlFor="referral-note">
            Note
            {(mode === 'correct' || form.needsNote) && (
              <span className="text-destructive"> *</span>
            )}
          </Label>
          <Textarea
            id="referral-note"
            maxLength={2000}
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
        </div>
      </FormModal>

      <FormModal
        open={assigning}
        onOpenChange={setAssigning}
        title="Reassign referral"
        description="Hand this referral to another officer. The change is recorded in the activity."
        submitLabel="Reassign"
        pending={assign.isPending}
        error={error}
        onSubmit={() => {
          if (!assignee) return setError('Choose an officer.');
          assign.mutate();
        }}
      >
        <SelectField
          label="Choose an officer"
          value={assignee}
          options={(people.data ?? []).map((p) => ({
            id: String(p.id),
            name: p.name,
          }))}
          onChange={setAssignee}
        />
      </FormModal>
    </div>
  );
}
