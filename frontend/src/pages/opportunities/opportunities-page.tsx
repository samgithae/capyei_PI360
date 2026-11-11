import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

interface Row {
  id: string;
  title: string;
  employer: string;
  kind: string;
  status: string;
  county: string;
  positions: number;
  closing_date: string | null;
}
interface Page {
  total: number;
  page_size: number;
  results: Row[];
}
interface EmployerPage {
  results: { id: string; name: string }[];
}

const KINDS = ['job', 'internship', 'apprenticeship', 'other'];
const STATUSES = ['draft', 'open', 'closed', 'expired'];

function AddForm({ onCancel }: { onCancel: () => void }) {
  const nav = useNavigate();
  const [search, setSearch] = useState('');
  const [v, setV] = useState({
    employer_id: '',
    title: '',
    kind: 'job',
    positions: '1',
    closing_date: '',
  });
  const [error, setError] = useState('');
  const employers = useQuery({
    queryKey: ['employer-search', search],
    queryFn: () =>
      api<EmployerPage>(`/employers?q=${encodeURIComponent(search)}`),
  });
  const create = useMutation({
    mutationFn: () =>
      post<{ id: string }>('/opportunities', {
        ...v,
        positions: Number(v.positions),
        closing_date: v.closing_date || null,
      }),
    onSuccess: (o) => nav(`/opportunities/${o.id}`),
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    create.mutate();
  };
  return (
    <form onSubmit={submit} className="max-w-xl space-y-3">
      <Input
        placeholder="Find employer by name"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <select
        aria-label="Employer"
        required
        className="h-9 w-full rounded-md border bg-background px-2 text-sm"
        value={v.employer_id}
        onChange={(e) => setV({ ...v, employer_id: e.target.value })}
      >
        <option value="">Choose employer</option>
        {employers.data?.results.map((e) => (
          <option key={e.id} value={e.id}>
            {e.name}
          </option>
        ))}
      </select>
      <Input
        aria-label="Title"
        placeholder="Title"
        required
        value={v.title}
        onChange={(e) => setV({ ...v, title: e.target.value })}
      />
      <div className="flex flex-wrap gap-2">
        <select
          aria-label="Type"
          className="h-8.5 rounded-md border border-input bg-background px-3 text-[0.8125rem] text-foreground shadow-xs shadow-black/5 outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/30"
          value={v.kind}
          onChange={(e) => setV({ ...v, kind: e.target.value })}
        >
          {KINDS.map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        <Input
          aria-label="Positions"
          type="number"
          min={1}
          className="w-24"
          value={v.positions}
          onChange={(e) => setV({ ...v, positions: e.target.value })}
        />
        <Input
          aria-label="Closing date"
          type="date"
          className="w-44"
          value={v.closing_date}
          onChange={(e) => setV({ ...v, closing_date: e.target.value })}
        />
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={create.isPending}>
          Save as draft
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function OpportunitiesPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const offset = Number(params.get('offset') ?? 0);
  const page = useQuery({
    queryKey: ['opportunities', params.toString()],
    queryFn: () => api<Page>(`/opportunities?${params.toString()}`),
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
        <title>Opportunities | PI 360</title>
      </Helmet>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>Opportunities</ToolbarPageTitle>
        </ToolbarHeading>
        {can('employers.edit') && !adding && (
          <Button onClick={() => setAdding(true)}>Add opportunity</Button>
        )}
      </Toolbar>
      {adding && <AddForm onCancel={() => setAdding(false)} />}
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
              placeholder="Search by title"
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="Any status"
              value={params.get('status') ?? ''}
              options={STATUSES.map((x) => ({ id: x, name: x }))}
              onChange={(v) => set('status', v)}
              className="w-36 capitalize"
            />
            <FilterSelect
              label="Any type"
              value={params.get('kind') ?? ''}
              options={KINDS.map((x) => ({ id: x, name: x }))}
              onChange={(v) => set('kind', v)}
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
                <TableHead>Title</TableHead>
                <TableHead>Employer</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Positions</TableHead>
                <TableHead>Closes</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((o) => (
                <TableRow key={o.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/opportunities/${o.id}`}
                    >
                      {o.title}
                    </Link>
                  </TableCell>
                  <TableCell>{o.employer}</TableCell>
                  <TableCell className="capitalize">{o.kind}</TableCell>
                  <TableCell>{o.positions}</TableCell>
                  <TableCell>{o.closing_date ?? ''}</TableCell>
                  <TableCell>
                    <ParticipantStatus status={o.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {data && data.results.length === 0 && (
          <div className="p-5">
            <EmptyState
              title="No opportunities match"
              hint="Try changing or clearing the filters."
            />
          </div>
        )}
      </DataCard>
    </div>
  );
}
