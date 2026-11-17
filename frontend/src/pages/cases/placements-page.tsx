import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { useSearchParams } from 'react-router';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  DataCard,
  FilterSelect,
  Pager,
  SearchBox,
} from '@/components/data-card';
import { SummaryStatCard } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import {
  PlacementDialog,
  usePlacementOptions,
  type PlacementPage,
  type PlacementSummary,
} from './case-shared';
import { PlacementTable } from './placement-table';

const STATES = [
  { id: 'current', name: 'Current' },
  { id: 'ended', name: 'Ended' },
  { id: 'unverified', name: 'Not verified' },
];

/** Placement outcomes (T-065): every employment or training episode, by pathway, with the
 * current status of each youth derived from their episodes. */
export function PlacementsPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const offset = Number(params.get('offset') ?? 0);
  const options = usePlacementOptions();
  const page = useQuery({
    queryKey: ['placements', params.toString()],
    queryFn: () => api<PlacementPage>(`/placements?${params.toString()}`),
  });
  const summary = useQuery({
    queryKey: ['placement-summary'],
    queryFn: () => api<PlacementSummary>('/placements/summary'),
  });
  const s = summary.data;
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const data = page.data;
  const filtered = ['q', 'pathway', 'state'].some((k) => params.get(k));

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Placements | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Placements' }]}
        title="Placements"
        description="Where youth ended up: wage work, self-employment, work-based learning or further training. A youth's current status comes from their episodes."
        actions={
          can('placements.edit') && (
            <Button onClick={() => setAdding(true)}>
              <Plus /> Record placement
            </Button>
          )
        }
      />
      {adding && <PlacementDialog open onOpenChange={setAdding} />}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <SummaryStatCard label="Current" value={s?.current} />
        <SummaryStatCard label="Ended" value={s?.ended} />
        <SummaryStatCard label="Not verified" value={s?.unverified} />
        <SummaryStatCard label="All episodes" value={s?.total} />
      </div>
      {s && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Object.entries(s.by_pathway).map(([code, p]) => (
            <SummaryStatCard
              key={code}
              label={`${p.label} (current)`}
              value={p.current}
            />
          ))}
        </div>
      )}

      <DataCard
        footer={
          data && data.total > 0 ? (
            <Pager
              offset={offset}
              pageSize={data.page_size}
              onPageSize={(n) => {
                const next = new URLSearchParams(params);
                next.set('page_size', String(n));
                next.delete('offset');
                setParams(next);
              }}
              total={data.total}
              onMove={(to) => {
                const next = new URLSearchParams(params);
                next.set('offset', String(Math.max(to, 0)));
                setParams(next);
              }}
            />
          ) : undefined
        }
        toolbar={
          <>
            <SearchBox
              placeholder="Search youth, employer or role"
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="Any pathway"
              value={params.get('pathway') ?? ''}
              options={(options.data?.pathways ?? []).map((p) => ({
                id: p.value,
                name: p.label,
              }))}
              onChange={(v) => set('pathway', v)}
              className="w-52"
            />
            <FilterSelect
              label="Any state"
              value={params.get('state') ?? ''}
              options={STATES}
              onChange={(v) => set('state', v)}
              className="w-40"
            />
          </>
        }
      >
        {page.isError && (
          <div className="p-5">
            <ErrorState error={page.error} onRetry={() => page.refetch()} />
          </div>
        )}
        {page.isPending && (
          <div className="p-5">
            <LoadingState />
          </div>
        )}
        {data && data.results.length === 0 && (
          <div className="p-5">
            <EmptyState
              title={filtered ? 'No placements match' : 'No placements yet'}
              hint={
                filtered
                  ? 'Try another pathway, state or search.'
                  : 'Record a placement here, or import them from the Imports page.'
              }
            />
          </div>
        )}
        {data && data.results.length > 0 && (
          <PlacementTable rows={data.results} />
        )}
      </DataCard>
    </div>
  );
}
