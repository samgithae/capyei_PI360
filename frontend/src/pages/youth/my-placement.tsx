import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { api } from '@/lib/api';
import { DataCard } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { MyPlacement } from './journey';

/** Where the learner ended up: placements on record and referrals that ended in a placement. */
export function MyPlacementPage() {
  const q = useQuery({
    queryKey: ['youth-placement'],
    queryFn: () => api<MyPlacement>('/youth/placement'),
    retry: false,
  });
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const { placements, referrals } = q.data;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>My placement</title>
      </Helmet>
      <PageHeader crumbs={[{ label: 'My placement' }]} title="My placement" />
      {placements.length === 0 && referrals.length === 0 ? (
        <EmptyState
          title="No placement yet"
          hint="When you are placed in a job, training or attachment, the details appear here."
        />
      ) : (
        <>
          {referrals.map((r) => (
            <DataCard key={r.id} title={r.designation}>
              <div className="space-y-1 p-5 text-sm">
                <p>{r.employer}</p>
                {r.location && <p>{r.location}</p>}
                {r.start_date && <p>Starts: {r.start_date}</p>}
                {r.placed_on && <p>Placed on: {r.placed_on}</p>}
              </div>
            </DataCard>
          ))}
          {placements.map((p) => (
            <DataCard key={p.id} title={p.designation || 'Placement'}>
              <div className="space-y-1 p-5 text-sm">
                <p>{p.employer}</p>
                {p.pathway && <p>{p.pathway}</p>}
                {p.start_date && <p>Started: {p.start_date}</p>}
              </div>
            </DataCard>
          ))}
        </>
      )}
    </div>
  );
}
