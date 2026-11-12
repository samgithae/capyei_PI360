import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { api } from '@/lib/api';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { Journey, JourneyDetail } from './journey';
import { StepTracker } from './step-tracker';

/** Every opportunity the learner has been referred to. */
export function MyOpportunitiesPage() {
  const q = useQuery({
    queryKey: ['youth-journey'],
    queryFn: () => api<Journey>('/youth/journey'),
    retry: false,
  });
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>My opportunities</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'My opportunities' }]}
        title="My opportunities"
      />
      {q.data.items.length === 0 ? (
        <EmptyState
          title="No opportunities yet"
          hint="When your officer refers you to a job, training or attachment, it will appear here."
        />
      ) : (
        <DataCard title="Referred to">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Opportunity</TableHead>
                <TableHead>Employer</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Referred</TableHead>
                <TableHead>Last update</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.items.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/me/opportunities/${r.id}`}
                    >
                      {r.opportunity}
                    </Link>
                  </TableCell>
                  <TableCell>{r.employer}</TableCell>
                  <TableCell>
                    <StatusBadge status={r.stage} label={r.stage_label} />
                  </TableCell>
                  <TableCell>{r.referred_at ?? ''}</TableCell>
                  <TableCell>{r.updated_at}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </DataCard>
      )}
    </div>
  );
}

/** One opportunity: where it stands, what it is and what has happened so far. */
export function MyOpportunityPage() {
  const { id } = useParams();
  const j = useQuery({
    queryKey: ['youth-journey'],
    queryFn: () => api<Journey>('/youth/journey'),
    retry: false,
  });
  const q = useQuery({
    queryKey: ['youth-opportunity', id],
    queryFn: () => api<JourneyDetail>(`/youth/opportunities/${id}`),
    retry: false,
  });
  if (q.isError)
    return (
      <div className="container-fluid space-y-3">
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        <Link className="text-sm text-primary" to="/me/opportunities">
          Back to my opportunities
        </Link>
      </div>
    );
  if (!q.data || !j.data) return <LoadingState />;
  const o = q.data;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>{o.opportunity}</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'My opportunities', to: '/me/opportunities' },
          { label: o.opportunity },
        ]}
        title={o.opportunity}
      />
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span>{o.employer}</span>
        <StatusBadge status={o.stage} label={o.stage_label} />
        {o.location && (
          <span className="text-muted-foreground">{o.location}</span>
        )}
        <span className="capitalize text-muted-foreground">{o.kind}</span>
      </div>
      <DataCard title="Where you are">
        <div className="p-5">
          <StepTracker steps={j.data.steps} item={o} />
        </div>
      </DataCard>
      {o.interview && (
        <DataCard title="Your interview">
          <div className="space-y-1 p-5 text-sm">
            <p>When: {new Date(o.interview.at).toLocaleString()}</p>
            {o.interview.place && <p>Where: {o.interview.place}</p>}
            {o.interview.note && <p>{o.interview.note}</p>}
          </div>
        </DataCard>
      )}
      <DataCard title="What has happened">
        <ul className="space-y-1 p-5 text-sm">
          {o.timeline.map((t, i) => (
            <li key={i}>
              <span className="text-muted-foreground">{t.at}</span> · {t.label}
            </li>
          ))}
        </ul>
      </DataCard>
      <DataCard title="About this opportunity">
        <div className="space-y-2 p-5 text-sm">
          {o.description ? (
            <p className="whitespace-pre-line">{o.description}</p>
          ) : (
            <p className="text-muted-foreground">No description given.</p>
          )}
          {o.start_date && <p>Starts: {o.start_date}</p>}
          {o.closing_date && <p>Applications close: {o.closing_date}</p>}
        </div>
      </DataCard>
      <Link className="text-sm text-primary" to="/me/opportunities">
        Back to my opportunities
      </Link>
    </div>
  );
}
