import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { api, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
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
  ParticipantStatus,
  SearchBox,
} from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { EmployerForm, EmployerValues, EMPTY, Options } from './employer-form';

interface Row {
  id: string;
  name: string;
  status: string;
  sector: string;
  county: string;
}
interface Page {
  total: number;
  page_size: number;
  results: Row[];
}

export function EmployersPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const offset = Number(params.get('offset') ?? 0);

  const options = useQuery({
    queryKey: ['employer-filters'],
    queryFn: () => api<Options>('/employers/filters'),
  });
  const page = useQuery({
    queryKey: ['employers', params.toString()],
    queryFn: () => api<Page>(`/employers?${params.toString()}`),
  });
  const create = useMutation({
    mutationFn: ({ v, confirm }: { v: EmployerValues; confirm: boolean }) =>
      post<{ id: string }>('/employers', { ...v, confirm_duplicate: confirm }),
    onSuccess: (e) => nav(`/employers/${e.id}`),
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const data = page.data;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Employers | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Employers' }]}
        title="Employers"
        description="Partner employers and their contacts."
        actions={
          can('employers.edit') &&
          !adding && (
            <Button onClick={() => setAdding(true)}>Add employer</Button>
          )
        }
      />

      {adding && (
        <EmployerForm
          initial={EMPTY}
          options={options.data}
          onCancel={() => setAdding(false)}
          onSave={async (v, confirm) => {
            await create.mutateAsync({ v, confirm });
          }}
        />
      )}

      <DataCard
        footer={
          data && data.total > data.page_size ? (
            <Pager
              offset={offset}
              pageSize={data.page_size}
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
              placeholder="Search by name"
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="All sectors"
              value={params.get('sector') ?? ''}
              options={options.data?.sectors ?? []}
              onChange={(v) => set('sector', v)}
            />
            <FilterSelect
              label="All counties"
              value={params.get('county') ?? ''}
              options={options.data?.counties ?? []}
              onChange={(v) => set('county', v)}
            />
            <FilterSelect
              label="Any status"
              value={params.get('status') ?? ''}
              options={['active', 'inactive', 'prospect'].map((x) => ({
                id: x,
                name: x,
              }))}
              onChange={(v) => set('status', v)}
              className="w-36 capitalize"
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
        {data && data.results.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Name</TableHead>
                <TableHead>Sector</TableHead>
                <TableHead>County</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/employers/${e.id}`}
                    >
                      {e.name}
                    </Link>
                  </TableCell>
                  <TableCell>{e.sector}</TableCell>
                  <TableCell>{e.county}</TableCell>
                  <TableCell>
                    <ParticipantStatus status={e.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {data && data.results.length === 0 && (
          <div className="p-5">
            <EmptyState
              title="No employers match"
              hint="Try changing or clearing the filters."
            />
          </div>
        )}
      </DataCard>
    </div>
  );
}
