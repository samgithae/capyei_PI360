import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';

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
          className="h-9 rounded-md border bg-background px-2 text-sm"
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
  const sel = (key: string, label: string, items: string[]) => (
    <select
      aria-label={label}
      className="h-9 rounded-md border bg-background px-2 text-sm"
      value={params.get(key) ?? ''}
      onChange={(e) => set(key, e.target.value)}
    >
      <option value="">{label}</option>
      {items.map((i) => (
        <option key={i}>{i}</option>
      ))}
    </select>
  );

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
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Search by title"
          defaultValue={params.get('q') ?? ''}
          onKeyDown={(e) => {
            if (e.key === 'Enter') set('q', e.currentTarget.value.trim());
          }}
          className="max-w-xs"
        />
        {sel('status', 'Any status', STATUSES)}
        {sel('kind', 'Any type', KINDS)}
      </div>
      {page.isError && <p role="alert">Could not load opportunities.</p>}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="py-2">Title</th>
            <th>Employer</th>
            <th>Type</th>
            <th>Positions</th>
            <th>Closes</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data?.results.map((o) => (
            <tr key={o.id} className="border-t">
              <td className="py-2">
                <Link className="text-primary" to={`/opportunities/${o.id}`}>
                  {o.title}
                </Link>
              </td>
              <td>{o.employer}</td>
              <td>{o.kind}</td>
              <td>{o.positions}</td>
              <td>{o.closing_date ?? ''}</td>
              <td>
                <Badge variant="secondary">{o.status}</Badge>
              </td>
            </tr>
          ))}
          {data && data.results.length === 0 && (
            <tr>
              <td
                colSpan={6}
                className="py-6 text-center text-muted-foreground"
              >
                No opportunities match.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {data && data.total > data.page_size && (
        <div className="flex items-center gap-3 text-sm">
          <span>
            {offset + 1}-{Math.min(offset + data.page_size, data.total)} of{' '}
            {data.total}
          </span>
          <Button
            variant="outline"
            disabled={offset === 0}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set('offset', String(Math.max(offset - data.page_size, 0)));
              setParams(next);
            }}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            disabled={offset + data.page_size >= data.total}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set('offset', String(offset + data.page_size));
              setParams(next);
            }}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
