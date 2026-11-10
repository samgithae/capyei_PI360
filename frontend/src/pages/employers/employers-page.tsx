import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { api, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
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
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>Employers</ToolbarPageTitle>
        </ToolbarHeading>
        {can('employers.edit') && !adding && (
          <Button onClick={() => setAdding(true)}>Add employer</Button>
        )}
      </Toolbar>

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

      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Search by name"
          defaultValue={params.get('q') ?? ''}
          onKeyDown={(e) => {
            if (e.key === 'Enter') set('q', e.currentTarget.value.trim());
          }}
          className="max-w-xs"
        />
        {(
          [
            ['sector', 'All sectors', options.data?.sectors],
            ['county', 'All counties', options.data?.counties],
          ] as const
        ).map(([key, label, items]) => (
          <select
            key={key}
            aria-label={label}
            className="h-9 rounded-md border bg-background px-2 text-sm"
            value={params.get(key) ?? ''}
            onChange={(e) => set(key, e.target.value)}
          >
            <option value="">{label}</option>
            {(items ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        ))}
        <select
          aria-label="Any status"
          className="h-9 rounded-md border bg-background px-2 text-sm"
          value={params.get('status') ?? ''}
          onChange={(e) => set('status', e.target.value)}
        >
          <option value="">Any status</option>
          {['active', 'inactive', 'prospect'].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>

      {page.isError && <p role="alert">Could not load employers.</p>}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="py-2">Name</th>
            <th>Sector</th>
            <th>County</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data?.results.map((e) => (
            <tr key={e.id} className="border-t">
              <td className="py-2">
                <Link className="text-primary" to={`/employers/${e.id}`}>
                  {e.name}
                </Link>
              </td>
              <td>{e.sector}</td>
              <td>{e.county}</td>
              <td>
                <Badge variant="secondary">{e.status}</Badge>
              </td>
            </tr>
          ))}
          {data && data.results.length === 0 && (
            <tr>
              <td
                colSpan={4}
                className="py-6 text-center text-muted-foreground"
              >
                No employers match.
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
            onClick={() =>
              set('offset', String(Math.max(offset - data.page_size, 0)))
            }
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
