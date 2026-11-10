import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useSearchParams } from 'react-router';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

interface Row {
  id: string;
  name: string;
  gender: string;
  age: number | null;
  status: string;
  county: string;
  programmes: string[];
  cohorts: string[];
}
interface Page {
  total: number;
  page_size: number;
  results: Row[];
}
interface Option {
  id: string;
  name: string;
  programme_id?: string;
}
interface Options {
  programmes: Option[];
  cohorts: Option[];
  counties: Option[];
}

const STATUSES = ['active', 'completed', 'withdrawn', 'unknown'];
const FILTERS = ['q', 'programme', 'cohort', 'county', 'status'] as const;

/** Youth directory. With a cohort chosen it doubles as the cohort roster (T-058). */
export function DirectoryPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') ?? 0);

  const options = useQuery({
    queryKey: ['participant-filters'],
    queryFn: () => api<Options>('/participants/filters'),
  });
  const page = useQuery({
    queryKey: ['participants', params.toString()],
    queryFn: () => api<Page>(`/participants?${params.toString()}`),
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const move = (to: number) => {
    const next = new URLSearchParams(params);
    next.set('offset', String(Math.max(to, 0)));
    setParams(next);
  };
  const cohorts = (options.data?.cohorts ?? []).filter(
    (c) =>
      !params.get('programme') || c.programme_id === params.get('programme'),
  );
  const select = (key: string, label: string, items: Option[]) => (
    <select
      aria-label={label}
      className="h-9 rounded-md border bg-background px-2 text-sm"
      value={params.get(key) ?? ''}
      onChange={(e) => set(key, e.target.value)}
    >
      <option value="">{label}</option>
      {items.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </select>
  );
  const data = page.data;
  const filtered = FILTERS.some((f) => params.get(f));

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Youth | PI 360</title>
      </Helmet>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>Youth</ToolbarPageTitle>
        </ToolbarHeading>
        {can('imports.run') && (
          <Button asChild>
            <Link to="/imports/new">Import participants</Link>
          </Button>
        )}
      </Toolbar>

      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Search name or enrollment no."
          defaultValue={params.get('q') ?? ''}
          onKeyDown={(e) => {
            if (e.key === 'Enter') set('q', e.currentTarget.value.trim());
          }}
          className="max-w-xs"
        />
        {select('programme', 'All programmes', options.data?.programmes ?? [])}
        {select('cohort', 'All cohorts', cohorts)}
        {select('county', 'All counties', options.data?.counties ?? [])}
        {select(
          'status',
          'Any status',
          STATUSES.map((s) => ({ id: s, name: s })),
        )}
        {filtered && (
          <Button variant="outline" onClick={() => setParams({})}>
            Clear
          </Button>
        )}
      </div>

      {page.isError && (
        <ErrorState error={page.error} onRetry={() => page.refetch()} />
      )}
      {page.isPending && <LoadingState />}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="py-2">Name</th>
            <th>Programme</th>
            <th>Cohort</th>
            <th>County</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data?.results.map((p) => (
            <tr key={p.id} className="border-t">
              <td className="py-2">
                <Link className="text-primary" to={`/youth/${p.id}`}>
                  {p.name}
                </Link>
              </td>
              <td>{p.programmes.join(', ')}</td>
              <td>{p.cohorts.join(', ')}</td>
              <td>{p.county}</td>
              <td>
                <Badge variant="secondary">{p.status}</Badge>
              </td>
            </tr>
          ))}
          {data && data.results.length === 0 && (
            <tr>
              <td colSpan={5}>
                <EmptyState
                  title="No participants match"
                  hint="Try changing or clearing the filters."
                />
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {data && data.total > 0 && (
        <div className="flex items-center gap-3 text-sm">
          <span>
            {offset + 1}-{Math.min(offset + data.page_size, data.total)} of{' '}
            {data.total}
          </span>
          <Button
            variant="outline"
            disabled={offset === 0}
            onClick={() => move(offset - data.page_size)}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            disabled={offset + data.page_size >= data.total}
            onClick={() => move(offset + data.page_size)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
