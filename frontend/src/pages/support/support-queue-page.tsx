import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { DataCard } from '@/components/data-card';
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

interface Flag {
  code: string;
  label: string;
  detail: string;
  days: number;
}
interface Item {
  participant_id: string;
  name: string;
  flags: Flag[];
  longest_days: number;
}
interface Queue {
  numbers: Record<string, number>;
  counts: { visible: number; flagged: number; paused: number };
  items: Item[];
  truncated: boolean;
  not_captured: string[];
  outcomes: Record<string, string>;
}

/** Module A: youth who may need extra support, with the plain fact behind each flag.
 * There is no score: a flag is a count or a number of days against a number set in Rules. */
export function SupportQueuePage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [target, setTarget] = useState<Item | null>(null);
  const [outcome, setOutcome] = useState('contacted');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const q = useQuery({
    queryKey: ['support-queue'],
    queryFn: () => api<Queue>('/support/queue'),
  });
  const review = useMutation({
    mutationFn: () =>
      api(`/participants/${target?.participant_id}/support-review`, {
        method: 'POST',
        body: JSON.stringify({
          outcome,
          note,
          flags: target?.flags.map((f) => f.code),
        }),
      }),
    onSuccess: () => {
      toast.success('Review recorded. The flag is paused for a while.');
      setTarget(null);
      setNote('');
      void qc.invalidateQueries({ queryKey: ['support-queue'] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const d = q.data;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Support priority | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Support priority' }]}
        title="Support priority"
        description="Youth who may need extra support, from what is recorded in PI 360. A flag is a fact, not a score; you decide what to do."
        actions={
          can('intelligence.view') && (
            <Button variant="outline" asChild>
              <Link to="/rules/settings">Change the numbers</Link>
            </Button>
          )
        }
      />
      <p className="text-sm text-muted-foreground">
        Flag when a youth has {d.numbers.unsuccessful} or more unsuccessful
        referrals in {d.numbers.window_days} days, an open referral with no
        movement for {d.numbers.stalled_days} days, or has been ready for work{' '}
        {d.numbers.unreferred_days} days without a referral. {d.counts.flagged}{' '}
        of {d.counts.visible} youth flagged
        {d.counts.paused > 0 && `, ${d.counts.paused} paused after a review`}.
      </p>
      {d.items.length === 0 ? (
        <EmptyState
          title="No one needs a look right now"
          hint="Youth appear here when a flag is raised and they have not been reviewed recently."
        />
      ) : (
        <DataCard title="To review">
          <ul className="divide-y">
            {d.items.map((i) => (
              <li
                key={i.participant_id}
                className="flex flex-wrap items-start justify-between gap-3 p-4"
              >
                <div className="space-y-1">
                  <Link
                    className="font-medium text-primary hover:underline"
                    to={`/youth/${i.participant_id}`}
                  >
                    {i.name}
                  </Link>
                  <ul className="text-sm">
                    {i.flags.map((f) => (
                      <li key={f.code}>
                        <span className="font-medium">{f.label}:</span>{' '}
                        <span className="text-muted-foreground">
                          {f.detail}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
                {can('referrals.edit') && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setError('');
                      setOutcome('contacted');
                      setNote('');
                      setTarget(i);
                    }}
                  >
                    Mark reviewed
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </DataCard>
      )}
      {d.truncated && (
        <p className="text-xs text-muted-foreground">
          Showing the first {d.items.length} only.
        </p>
      )}
      <div className="rounded-md border p-3 text-xs text-muted-foreground">
        Not checked yet because PI 360 does not hold the data:{' '}
        {d.not_captured.join('; ')}.
      </div>
      <FormModal
        open={target !== null}
        onOpenChange={(o) => !o && setTarget(null)}
        title={`Review ${target?.name ?? ''}`}
        description="Say what you did. The flag stays hidden for a few days, then returns if it still applies."
        submitLabel="Record review"
        pending={review.isPending}
        error={error}
        onSubmit={() => {
          setError('');
          review.mutate();
        }}
      >
        <div className="space-y-3">
          <SelectField
            label="What did you do?"
            value={outcome}
            options={Object.entries(d.outcomes).map(([id, name]) => ({
              id,
              name,
            }))}
            onChange={setOutcome}
          />
          <div className="space-y-1">
            <Label htmlFor="review-note">
              Note{outcome === 'no_action' ? ' (required)' : ' (optional)'}
            </Label>
            <Textarea
              id="review-note"
              value={note}
              maxLength={500}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </div>
      </FormModal>
    </div>
  );
}
