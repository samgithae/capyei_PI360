import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useSearchParams } from 'react-router';
import { api } from '@/lib/api';
import { DataCard, Pager } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { Drill } from './dashboard-types';

/** The records behind one dashboard number. The count on the dashboard is the total here. */
export function DashboardListPage() {
  const [sp] = useSearchParams();
  const key = sp.get('key') ?? '';
  const period = sp.get('period') ?? '90';
  const title = sp.get('title') ?? 'Records';
  const [offset, setOffset] = useState(0);
  const [size, setSize] = useState(30);
  const q = useQuery({
    queryKey: ['dashboard-list', key, period, offset, size],
    queryFn: () =>
      api<Drill>(
        `/reporting/drilldown?key=${encodeURIComponent(key)}&period=${period}&offset=${offset}&page_size=${size}`,
      ),
  });
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const d = q.data;
  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>{title} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Dashboard', to: '/' }, { label: title }]}
        title={title}
        description={`${d.total} record${d.total === 1 ? '' : 's'} behind this number, limited to what you may see.`}
      />
      {d.total === 0 ? (
        <EmptyState title="Nothing to list" hint="No records match." />
      ) : (
        <DataCard
          footer={
            <Pager
              offset={offset}
              pageSize={size}
              total={d.total}
              onMove={setOffset}
              onPageSize={(n) => {
                setSize(n);
                setOffset(0);
              }}
            />
          }
        >
          <ul className="divide-y">
            {d.results.map((r) => (
              <li key={r.id} className="p-4">
                <Link
                  className="font-medium text-primary hover:underline"
                  to={r.link}
                >
                  {r.name}
                </Link>
                {r.detail && (
                  <div className="text-sm text-muted-foreground">
                    {r.detail}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </DataCard>
      )}
    </div>
  );
}
