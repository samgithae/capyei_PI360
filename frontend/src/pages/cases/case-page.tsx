import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useParams } from 'react-router';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
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
  AssignDialog,
  InterventionDialog,
  MoveDialog,
  type InterventionDetail,
} from './case-shared';

// Button text for moving to each status.
const MOVE_LABEL: Record<string, string> = {
  open: 'Reopen',
  in_progress: 'Start work',
  awaiting_verification: 'Awaiting verification',
  closed: 'Close',
  cancelled: 'Cancel intervention',
};

/** One intervention: details, the next steps allowed, follow-ups and the audited history (T-064). */
export function CasePage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [move, setMove] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);
  const [editing, setEditing] = useState(false);
  const [followUp, setFollowUp] = useState(false);

  const q = useQuery({
    queryKey: ['intervention', id],
    queryFn: () => api<InterventionDetail>(`/interventions/${id}`),
  });
  const history = useQuery({
    queryKey: ['intervention-history', id],
    queryFn: () => api<AuditEvent[]>(`/interventions/${id}/history`),
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
  const i = q.data;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>{i.title} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Cases', to: '/cases' }, { label: i.title }]}
        title={i.title}
        badges={
          <>
            <StatusBadge status={i.status} label={i.status_label} />
            {i.overdue && (
              <Badge variant="destructive" appearance="light">
                Overdue
              </Badge>
            )}
          </>
        }
        description={`For ${i.participant}`}
        actions={
          <>
            {i.can.edit &&
              i.next_statuses.map((s) => (
                <Button
                  key={s}
                  variant={s === 'cancelled' ? 'outline' : 'primary'}
                  onClick={() => setMove(s)}
                >
                  {MOVE_LABEL[s] ?? s}
                </Button>
              ))}
            {i.can.edit && (
              <Button variant="outline" onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
            {i.can.reassign && (
              <Button variant="outline" onClick={() => setAssigning(true)}>
                Reassign
              </Button>
            )}
            {i.can.follow_up && (
              <Button variant="outline" onClick={() => setFollowUp(true)}>
                Add follow-up
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
              value: (
                <Link
                  className="text-primary hover:underline"
                  to={`/youth/${i.participant_id}`}
                >
                  {i.participant}
                </Link>
              ),
            },
            { label: 'Kind of support', value: i.need_label },
            { label: 'Owner', value: i.owner },
            { label: 'Due', value: i.due_date },
            { label: 'Details', value: i.detail },
            { label: 'Recorded by', value: i.created_by },
            {
              label: 'Verified how',
              value: i.verification_source_label,
            },
            { label: 'Outcome note', value: i.outcome_note },
          ]}
        />
        {i.follow_up_of_id && (
          <p className="mt-4 text-sm">
            This is a follow-up.{' '}
            <Link
              className="text-primary hover:underline"
              to={`/cases/${i.follow_up_of_id}`}
            >
              See the earlier intervention
            </Link>
          </p>
        )}
      </Section>

      {i.follow_ups.length > 0 && (
        <Section title="Follow-ups">
          <ul className="divide-y divide-border text-sm">
            {i.follow_ups.map((f) => (
              <li key={f.id} className="flex justify-between gap-2 py-2">
                <Link
                  className="font-medium text-foreground hover:text-primary"
                  to={`/cases/${f.id}`}
                >
                  {f.title}
                </Link>
                <span className="text-muted-foreground">{f.status_label}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="History">
        {history.isPending ? (
          <LoadingState rows={3} />
        ) : (
          <ActivityTimeline events={history.data ?? []} />
        )}
      </Section>

      {move && (
        <MoveDialog
          open
          onOpenChange={(o) => !o && setMove(null)}
          intervention={i}
          to={move}
        />
      )}
      {assigning && (
        <AssignDialog open onOpenChange={setAssigning} intervention={i} />
      )}
      {editing && (
        <InterventionDialog open onOpenChange={setEditing} edit={i} />
      )}
      {followUp && (
        <InterventionDialog
          open
          onOpenChange={setFollowUp}
          followUpOf={{
            id: i.id,
            participant: i.participant,
            title: i.title,
          }}
          onSaved={(newId) => nav(`/cases/${newId}`)}
        />
      )}
    </div>
  );
}
