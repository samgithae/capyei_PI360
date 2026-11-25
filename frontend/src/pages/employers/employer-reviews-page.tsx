import { useState } from 'react';
import { errorText } from '@/pages/cases/case-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { api, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

export interface Review {
  id: string;
  employer_id: string;
  employer: string;
  opened_on: string;
  reasons: string[];
  ratings_count: number;
  status: 'open' | 'closed';
  outcome: '' | 'monitor' | 'ignore';
  outcome_label: string;
  reason: string;
  decided_by: string;
  decided_at: string | null;
}

const TABS = [
  ['open', 'Open'],
  ['closed', 'Decided'],
] as const;

/** The employer review queue (NEW-028). A review is opened by the nightly check when recent
 * ratings are low. An administrator records Monitor or Ignore with a reason; nothing here
 * suspends or changes an employer (D-078). */
export function EmployerReviewsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<'open' | 'closed'>('open');
  const [deciding, setDeciding] = useState<Review | null>(null);
  const [outcome, setOutcome] = useState<'monitor' | 'ignore'>('monitor');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['employer-reviews', tab],
    queryFn: () =>
      api<{ results: Review[] }>(`/employers/reviews?status=${tab}`),
  });
  const decide = useMutation({
    mutationFn: () =>
      post(`/employers/reviews/${deciding?.id}/decision`, {
        outcome,
        reason: reason.trim(),
      }),
    onSuccess: () => {
      toast.success('Decision recorded');
      setDeciding(null);
      setReason('');
      void qc.invalidateQueries({ queryKey: ['employer-reviews'] });
    },
    onError: (e) => setError(errorText(e)),
  });

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Employer reviews | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Employers', to: '/employers' },
          { label: 'Reviews' },
        ]}
        title="Employer reviews"
        description="Employers whose recent ratings are low. Choose Monitor or Ignore and say why. Nothing here suspends an employer or changes their suggestions."
      />
      <div className="flex gap-2">
        {TABS.map(([v, l]) => (
          <Button
            key={v}
            size="sm"
            variant={tab === v ? 'primary' : 'outline'}
            onClick={() => setTab(v)}
          >
            {l}
          </Button>
        ))}
      </div>
      {list.isLoading && <LoadingState />}
      {list.isError && <ErrorState />}
      {list.data && list.data.results.length === 0 && (
        <EmptyState
          title={tab === 'open' ? 'No open reviews' : 'No decisions yet'}
          hint="Reviews appear here only when automatic alerts are switched on and an employer's ratings are low."
        />
      )}
      {list.data?.results.map((r) => (
        <Card key={r.id}>
          <CardContent className="space-y-2 p-4 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Link
                to={`/employers/${r.employer_id}`}
                className="font-medium underline"
              >
                {r.employer}
              </Link>
              <span className="text-muted-foreground">
                Opened {r.opened_on}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {r.reasons.map((x) => (
                <Badge key={x} variant="warning" appearance="light">
                  {x}
                </Badge>
              ))}
              <span className="text-muted-foreground">
                {r.ratings_count} ratings counted
              </span>
            </div>
            {r.status === 'open' ? (
              <Button
                size="sm"
                onClick={() => {
                  setDeciding(r);
                  setError('');
                }}
              >
                Record a decision
              </Button>
            ) : (
              <p>
                <strong>{r.outcome_label}</strong> by {r.decided_by}
                {r.decided_at && ` on ${r.decided_at.slice(0, 10)}`}: {r.reason}
              </p>
            )}
          </CardContent>
        </Card>
      ))}
      <FormModal
        open={deciding !== null}
        onOpenChange={(o) => !o && setDeciding(null)}
        title={`Review of ${deciding?.employer ?? ''}`}
        description="Monitor keeps the employer as they are and keeps watching. Ignore closes the review with no follow-up. Neither suspends the employer."
        submitLabel="Record decision"
        pending={decide.isPending}
        error={error}
        onSubmit={() => decide.mutate()}
      >
        <div className="space-y-1.5">
          <Label htmlFor="rv-outcome">Decision</Label>
          <select
            id="rv-outcome"
            className="block h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as 'monitor' | 'ignore')}
          >
            <option value="monitor">Monitor</option>
            <option value="ignore">Ignore</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rv-reason">Reason</Label>
          <Textarea
            id="rv-reason"
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
      </FormModal>
    </div>
  );
}
