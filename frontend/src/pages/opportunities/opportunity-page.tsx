import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

interface Requirement {
  id: string;
  factor: string;
  description: string;
  is_mandatory: boolean;
}
interface Detail {
  id: string;
  title: string;
  employer_id: string;
  employer: string;
  kind: string;
  status: string;
  sector: string;
  county: string;
  location: string;
  positions: number;
  description: string;
  start_date: string | null;
  closing_date: string | null;
  requirements: Requirement[];
}
interface Event {
  at: string;
  actor: string;
  action: string;
}

const FACTORS = ['skill', 'qualification', 'location', 'availability', 'other'];
const NEXT: Record<string, { to: string; label: string }[]> = {
  draft: [{ to: 'open', label: 'Open' }],
  open: [{ to: 'closed', label: 'Close' }],
  closed: [{ to: 'open', label: 'Reopen' }],
  expired: [{ to: 'open', label: 'Reopen' }],
};

export function OpportunityPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const canEdit = can('employers.edit');
  const [error, setError] = useState('');
  const [closing, setClosing] = useState('');
  const [req, setReq] = useState({
    factor: 'skill',
    description: '',
    is_mandatory: false,
  });

  const refresh = () => {
    setError('');
    void qc.invalidateQueries({ queryKey: ['opportunity', id] });
    void qc.invalidateQueries({ queryKey: ['opportunity-history', id] });
  };
  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'Something went wrong.');

  const q = useQuery({
    queryKey: ['opportunity', id],
    queryFn: () => api<Detail>(`/opportunities/${id}`),
    retry: false,
  });
  const history = useQuery({
    queryKey: ['opportunity-history', id],
    queryFn: () => api<Event[]>(`/opportunities/${id}/history`),
  });
  const move = useMutation({
    mutationFn: (to: string) => post(`/opportunities/${id}/transition`, { to }),
    onSuccess: refresh,
    onError: fail,
  });
  const setDate = useMutation({
    mutationFn: () =>
      api(`/opportunities/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ closing_date: closing || null }),
      }),
    onSuccess: () => {
      setClosing('');
      refresh();
    },
    onError: fail,
  });
  const addReq = useMutation({
    mutationFn: () => post(`/opportunities/${id}/requirements`, req),
    onSuccess: () => {
      setReq({ ...req, description: '' });
      refresh();
    },
    onError: fail,
  });
  const delReq = useMutation({
    mutationFn: (rid: string) =>
      api(`/opportunities/${id}/requirements/${rid}`, { method: 'DELETE' }),
    onSuccess: refresh,
    onError: fail,
  });
  const flip = useMutation({
    mutationFn: (r: Requirement) =>
      api(`/opportunities/${id}/requirements/${r.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_mandatory: !r.is_mandatory }),
      }),
    onSuccess: refresh,
    onError: fail,
  });

  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Opportunity not found"
            hint="It may have been removed or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        <Link className="text-primary" to="/opportunities">
          Back to opportunities
        </Link>
      </div>
    );
  }
  const o = q.data;
  if (!o) return <LoadingState />;
  const locked = o.status === 'closed' || o.status === 'expired';

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{o.title} | PI 360</title>
      </Helmet>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>{o.title}</ToolbarPageTitle>
        </ToolbarHeading>
        {canEdit &&
          NEXT[o.status]?.map((n) => (
            <Button
              key={n.to}
              variant="outline"
              disabled={move.isPending}
              onClick={() => move.mutate(n.to)}
            >
              {n.label}
            </Button>
          ))}
      </Toolbar>
      {error && <p role="alert">{error}</p>}

      <div className="flex flex-wrap gap-3 text-sm">
        <Badge variant="secondary">{o.status}</Badge>
        <Link className="text-primary" to={`/employers/${o.employer_id}`}>
          {o.employer}
        </Link>
        <span>{o.kind}</span>
        <span>{o.positions} position(s)</span>
        {o.sector && <span>{o.sector}</span>}
        {o.county && <span>{o.county}</span>}
        {o.location && <span>{o.location}</span>}
        <span>Closes {o.closing_date ?? 'not set'}</span>
      </div>
      {o.description && <p className="text-sm">{o.description}</p>}

      {canEdit && !locked && (
        <form
          className="flex items-center gap-2"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            setDate.mutate();
          }}
        >
          <Input
            aria-label="New closing date"
            type="date"
            className="w-44"
            value={closing}
            onChange={(e) => setClosing(e.target.value)}
            required
          />
          <Button type="submit" variant="outline">
            Set closing date
          </Button>
        </form>
      )}

      <section>
        <h2 className="mb-2 font-semibold">Requirements</h2>
        <ul className="space-y-1 text-sm">
          {o.requirements.map((r) => (
            <li key={r.id} className="flex items-center gap-3">
              <Badge variant={r.is_mandatory ? 'default' : 'secondary'}>
                {r.is_mandatory ? 'Mandatory' : 'Preferred'}
              </Badge>
              <span>
                {r.factor}: {r.description}
              </span>
              {canEdit && !locked && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => flip.mutate(r)}
                  >
                    Make {r.is_mandatory ? 'preferred' : 'mandatory'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => delReq.mutate(r.id)}
                  >
                    Remove
                  </Button>
                </>
              )}
            </li>
          ))}
          {o.requirements.length === 0 && (
            <li className="text-muted-foreground">No requirements yet.</li>
          )}
        </ul>
        {canEdit && !locked && (
          <form
            className="mt-3 flex flex-wrap items-center gap-2"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              addReq.mutate();
            }}
          >
            <select
              aria-label="Factor"
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={req.factor}
              onChange={(e) => setReq({ ...req, factor: e.target.value })}
            >
              {FACTORS.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
            <Input
              aria-label="Requirement"
              placeholder="Requirement"
              required
              className="w-64"
              value={req.description}
              onChange={(e) => setReq({ ...req, description: e.target.value })}
            />
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={req.is_mandatory}
                onChange={(e) =>
                  setReq({ ...req, is_mandatory: e.target.checked })
                }
              />
              Mandatory
            </label>
            <Button type="submit">Add requirement</Button>
          </form>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">History</h2>
        <ul className="space-y-1 text-sm">
          {history.data?.map((h, i) => (
            <li key={i}>
              {new Date(h.at).toLocaleString()} - {h.actor}: {h.action}
            </li>
          ))}
        </ul>
      </section>
      <Link className="text-primary text-sm" to="/opportunities">
        Back to opportunities
      </Link>
    </div>
  );
}
