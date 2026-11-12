import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useSearchParams } from 'react-router';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DataCard,
  FilterSelect,
  Pager,
  SearchBox,
} from '@/components/data-card';
import { RowActions } from '@/components/shared/bulk';
import { SummaryStatCard } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import {
  ACTIVE,
  ReferDialog,
  STAGES,
  UNSUCCESSFUL,
  type ReferralPage,
} from './referral-shared';

const STAGE_FILTER = [{ id: 'active', name: 'Still in progress' }, ...STAGES];
const day = (iso: string | null) => (iso ? iso.slice(0, 10) : '');

/** Referrals list (T-046). Shows only referrals for youth inside the user's scope. */
export function ReferralsPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const offset = Number(params.get('offset') ?? 0);
  // The URL is the single source of truth for filters: the query key includes it, so
  // React Query refetches whenever a filter changes and Back restores the old view.
  const page = useQuery({
    queryKey: ['referrals', params.toString()],
    queryFn: () => api<ReferralPage>(`/referrals?${params.toString()}`),
  });
  const summary = useQuery({
    queryKey: ['referral-summary'],
    queryFn: () => api<Record<string, number>>('/referrals/summary'),
  });
  const sum = (stages: string[]) =>
    summary.data
      ? stages.reduce((n, s) => n + (summary.data[s] ?? 0), 0)
      : undefined;
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const data = page.data;
  const filtered = ['q', 'stage', 'mine'].some((k) => params.get(k));

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Referrals | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Referrals' }]}
        title="Referrals"
        description="Youth put forward for opportunities, and where each referral stands."
        actions={
          can('referrals.edit') && (
            <Button onClick={() => setAdding(true)}>
              <Plus /> Refer youth
            </Button>
          )
        }
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <SummaryStatCard label="In progress" value={sum(ACTIVE)} />
        <SummaryStatCard
          label="Interview or selected"
          value={sum(['interview', 'selected'])}
        />
        <SummaryStatCard label="Placed" value={sum(['placed'])} />
        <SummaryStatCard label="Unsuccessful" value={sum(UNSUCCESSFUL)} />
      </div>
      <ReferDialog open={adding} onOpenChange={setAdding} />
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
              placeholder="Search youth, opportunity or employer"
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="Any stage"
              value={params.get('stage') ?? ''}
              options={STAGE_FILTER}
              onChange={(v) => set('stage', v)}
              className="w-48"
            />
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox
                aria-label="Only mine"
                checked={params.get('mine') === '1'}
                onCheckedChange={(v) => set('mine', v === true ? '1' : '')}
              />
              Only mine
            </label>
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
              title={filtered ? 'No referrals match' : 'No referrals yet'}
              hint={
                filtered
                  ? 'Try another stage or search.'
                  : 'Refer a youth from their profile or from an opportunity.'
              }
            />
          </div>
        )}
        {data && data.results.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Youth</TableHead>
                <TableHead>Opportunity</TableHead>
                <TableHead>Employer</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Assigned to</TableHead>
                <TableHead>Referred</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/referrals/${r.id}`}
                    >
                      {r.participant}
                    </Link>
                  </TableCell>
                  <TableCell>{r.opportunity}</TableCell>
                  <TableCell>{r.employer}</TableCell>
                  <TableCell>
                    <StatusBadge status={r.stage} label={r.stage_label} />
                    {r.reason && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {r.reason}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>{r.assigned_to}</TableCell>
                  <TableCell>{day(r.referred_at)}</TableCell>
                  <TableCell>
                    <RowActions
                      label={`${r.participant}, ${r.opportunity}`}
                      viewTo={`/referrals/${r.id}`}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DataCard>
    </div>
  );
}
