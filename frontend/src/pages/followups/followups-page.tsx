import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useSearchParams } from 'react-router';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  DataCard,
  FilterSelect,
  Pager,
  SearchBox,
} from '@/components/data-card';
import { ExportButton } from '@/components/shared/export-button';
import { SummaryStatCard } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import {
  KIND_OPTIONS,
  type FollowUpPage,
  type FollowUpSummary,
} from './followup-shared';
import { FollowUpTable } from './followup-table';

const STATES = [
  { id: 'open', name: 'Open' },
  { id: 'overdue', name: 'Overdue' },
  { id: 'due_soon', name: 'Due in 7 days' },
  { id: 'done', name: 'Done' },
  { id: 'closed', name: 'Closed (any outcome)' },
  { id: 'all', name: 'Everything' },
];

/** Post-placement follow-up (T-066): the check-ins generated when a placement is confirmed.
 * Early follow-ups come at 30 and 90 days by default, tracer follow-ups up to 24 months. */
export function FollowUpsPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') ?? 0);
  const mine = params.get('mine') === '1';
  const list = useQuery({
    queryKey: ['followups', params.toString()],
    queryFn: () => api<FollowUpPage>(`/followups?${params.toString()}`),
  });
  const summary = useQuery({
    queryKey: ['followup-summary', mine],
    queryFn: () =>
      api<FollowUpSummary>(`/followups/summary?mine=${mine ? 1 : 0}`),
  });
  const s = summary.data;
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const data = list.data;
  const filtered = ['q', 'kind', 'state'].some((k) => params.get(k));

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Follow-ups | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Follow-ups' }]}
        title="Follow-ups"
        description="Check-ins after a placement: early ones soon after it starts, tracer ones months later. Each records who tried, what the youth said and how it was confirmed."
        actions={
          <>
            <div
              role="group"
              aria-label="Whose work"
              className="inline-flex rounded-md border"
            >
              <Button
                variant={mine ? 'ghost' : 'primary'}
                aria-pressed={!mine}
                onClick={() => set('mine', '')}
              >
                Everyone
              </Button>
              <Button
                variant={mine ? 'primary' : 'ghost'}
                aria-pressed={mine}
                onClick={() => set('mine', '1')}
              >
                Mine
              </Button>
            </div>
            {can('config.view') && (
              <Button variant="outline" asChild>
                <Link to="/administration/followup-schedule">Schedule</Link>
              </Button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <SummaryStatCard label="Open" value={s?.open} />
        <SummaryStatCard label="Overdue" value={s?.overdue} />
        <SummaryStatCard label="Due in the next 7 days" value={s?.due_soon} />
        <SummaryStatCard label="Done" value={s?.done} />
      </div>
      {s && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Object.entries(s.by_kind).map(([code, k]) => (
            <SummaryStatCard
              key={code}
              label={`${k.label}: open`}
              value={k.open}
            />
          ))}
          {Object.entries(s.by_kind).map(([code, k]) => (
            <SummaryStatCard
              key={`${code}-done`}
              label={`${k.label}: done`}
              value={k.done}
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
              placeholder="Search youth"
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="Any kind"
              value={params.get('kind') ?? ''}
              options={KIND_OPTIONS}
              onChange={(v) => set('kind', v)}
              className="w-44"
            />
            <FilterSelect
              label="Open"
              value={params.get('state') ?? ''}
              options={STATES}
              onChange={(v) => set('state', v)}
              className="w-48"
            />
            <ExportButton
              table="followups"
              params={params}
              noun="follow-ups"
              total={data?.total}
            />
          </>
        }
      >
        {list.isError && (
          <div className="p-5">
            <ErrorState error={list.error} onRetry={() => list.refetch()} />
          </div>
        )}
        {list.isPending && (
          <div className="p-5">
            <LoadingState />
          </div>
        )}
        {data && data.results.length === 0 && (
          <div className="p-5">
            <EmptyState
              title={filtered ? 'No follow-ups match' : 'No follow-ups to do'}
              hint={
                filtered
                  ? 'Try another kind, state or search.'
                  : 'Check-ins appear here when a placement is recorded with a start date, or verified.'
              }
            />
          </div>
        )}
        {data && data.results.length > 0 && (
          <FollowUpTable rows={data.results} />
        )}
      </DataCard>
    </div>
  );
}
