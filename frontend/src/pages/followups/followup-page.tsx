import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  ActivityTimeline,
  type AuditEvent,
} from '@/components/shared/activity-timeline';
import { DetailList, Section } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { ErrorState, LoadingState } from '@/components/states';
import {
  AssignFollowUpDialog,
  AttemptDialog,
  CancelDialog,
  CompleteDialog,
  OverdueBadge,
  UnreachableDialog,
  type FollowUpDetail,
} from './followup-shared';

type Dialog = 'attempt' | 'complete' | 'unreachable' | 'cancel' | 'assign';

/** One check-in: what it is, every attempt, the response and evidence, and the history. */
export function FollowUpPage() {
  const { id } = useParams();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const q = useQuery({
    queryKey: ['followup', id],
    queryFn: () => api<FollowUpDetail>(`/followups/${id}`),
  });
  const history = useQuery({
    queryKey: ['followup-history', id],
    queryFn: () => api<AuditEvent[]>(`/followups/${id}/history`),
  });

  if (q.isError)
    return (
      <div className="container-fluid">
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </div>
    );
  if (!q.data)
    return (
      <div className="container-fluid">
        <LoadingState />
      </div>
    );
  const f = q.data;
  const close = (o: boolean) => !o && setDialog(null);
  const title = `${f.label} check-in`;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>{title} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Follow-ups', to: '/followups' },
          { label: `${f.participant}: ${f.label}` },
        ]}
        title={title}
        badges={
          <>
            <StatusBadge status={f.status} label={f.status_label} />
            <OverdueBadge row={f} />
          </>
        }
        description={`For ${f.participant}. ${f.kind_label}, due ${f.due_date}.`}
        actions={
          <>
            {f.can.work && (
              <>
                <Button onClick={() => setDialog('attempt')}>
                  Log an attempt
                </Button>
                <Button variant="outline" onClick={() => setDialog('complete')}>
                  Record the response
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setDialog('unreachable')}
                >
                  Unreachable
                </Button>
                <Button variant="outline" onClick={() => setDialog('cancel')}>
                  Cancel
                </Button>
              </>
            )}
            {f.can.assign && (
              <Button variant="outline" onClick={() => setDialog('assign')}>
                Reassign
              </Button>
            )}
          </>
        }
      />

      <Section title="Details">
        <DetailList
          items={[
            {
              label: 'Youth',
              value: f.participant_id ? (
                <Link
                  className="text-primary hover:underline"
                  to={`/youth/${f.participant_id}`}
                >
                  {f.participant}
                </Link>
              ) : (
                f.participant
              ),
            },
            {
              label: 'Placement',
              value: [f.designation, f.employer].filter(Boolean).join(' at '),
            },
            { label: 'Placement started', value: f.placement_start },
            { label: 'Owner', value: f.assigned_to },
            { label: 'Next action', value: f.next_action },
            { label: 'Next action date', value: f.next_action_date },
          ]}
        />
        {f.placement_ended && (
          <p className="mt-4 text-sm text-muted-foreground">
            The placement has ended. If this check-in no longer applies, cancel
            it with a reason.
          </p>
        )}
      </Section>

      {f.status !== 'open' && (
        <Section title="Outcome">
          <DetailList
            items={[
              {
                label: 'Still in the placement',
                value:
                  f.still_employed === null
                    ? ''
                    : f.still_employed
                      ? 'Yes'
                      : 'No',
              },
              { label: 'Confirmed by', value: f.evidence_source_label },
              { label: 'Note', value: f.response_note },
              { label: 'Closed by', value: f.closed_by },
              {
                label: 'Closed on',
                value: f.closed_at
                  ? new Date(f.closed_at).toLocaleDateString()
                  : '',
              },
            ]}
          />
        </Section>
      )}

      <Section title={`Attempts (${f.attempt_list.length})`}>
        {f.attempt_list.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No attempts yet. Log one each time you try to reach the youth.
          </p>
        ) : (
          <ul className="divide-y divide-border text-sm">
            {f.attempt_list.map((a) => (
              <li key={a.id} className="space-y-0.5 py-3">
                <p className="font-medium">
                  {a.method_label}
                  <span className="font-normal text-muted-foreground">
                    {' '}
                    &middot; {a.reached
                      ? 'Reached'
                      : 'Not reached'} &middot; {a.made_on} &middot; {a.made_by}
                  </span>
                </p>
                {a.note && <p className="break-words">{a.note}</p>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="History">
        {history.isPending ? (
          <LoadingState rows={3} />
        ) : (
          <ActivityTimeline events={history.data ?? []} />
        )}
      </Section>

      {dialog === 'attempt' && (
        <AttemptDialog open onOpenChange={close} followup={f} />
      )}
      {dialog === 'complete' && (
        <CompleteDialog open onOpenChange={close} followup={f} />
      )}
      {dialog === 'unreachable' && (
        <UnreachableDialog open onOpenChange={close} followup={f} />
      )}
      {dialog === 'cancel' && (
        <CancelDialog open onOpenChange={close} followup={f} />
      )}
      {dialog === 'assign' && (
        <AssignFollowUpDialog open onOpenChange={close} followup={f} />
      )}
    </div>
  );
}
