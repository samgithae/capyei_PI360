import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ActivityTimeline } from '@/components/shared/activity-timeline';
import { DetailList, Section } from '@/components/shared/info-card';
import { ConfirmDialog, FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
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
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
}

const FACTORS = ['skill', 'qualification', 'location', 'availability', 'other'];
const NEXT: Record<string, { to: string; label: string }[]> = {
  draft: [{ to: 'open', label: 'Open' }],
  open: [{ to: 'closed', label: 'Close' }],
  closed: [{ to: 'open', label: 'Reopen' }],
  expired: [{ to: 'open', label: 'Reopen' }],
};
const BLANK = { factor: 'skill', description: '', is_mandatory: false };

export function OpportunityPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const canEdit = can('employers.edit');
  const [error, setError] = useState('');
  const [dateOpen, setDateOpen] = useState(false);
  const [closing, setClosing] = useState('');
  const [reqOpen, setReqOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [req, setReq] = useState(BLANK);
  const [removing, setRemoving] = useState<Requirement | null>(null);
  const [confirmMove, setConfirmMove] = useState<string | null>(null);

  const refresh = () => {
    setError('');
    void qc.invalidateQueries({ queryKey: ['opportunity', id] });
    void qc.invalidateQueries({ queryKey: ['opportunity-history', id] });
    void qc.invalidateQueries({ queryKey: ['opportunities'] });
    void qc.invalidateQueries({ queryKey: ['opportunity-count'] });
  };
  const fail = (e: unknown) => {
    const m = e instanceof ApiError ? e.message : 'Something went wrong.';
    setError(m);
    toast.error(m);
  };

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
    onSuccess: (_d, to) => {
      toast.success(`Opportunity is now ${to}.`);
      refresh();
    },
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
      setDateOpen(false);
      toast.success('Closing date saved.');
      refresh();
    },
    onError: fail,
  });
  // One mutation for add and edit: a requirement id means PATCH, none means POST.
  const saveReq = useMutation({
    mutationFn: () =>
      editingId
        ? api(`/opportunities/${id}/requirements/${editingId}`, {
            method: 'PATCH',
            body: JSON.stringify(req),
          })
        : post(`/opportunities/${id}/requirements`, req),
    onSuccess: () => {
      toast.success(editingId ? 'Requirement updated.' : 'Requirement added.');
      setReqOpen(false);
      setReq(BLANK);
      setEditingId(null);
      refresh();
    },
    onError: fail,
  });
  const delReq = useMutation({
    mutationFn: (rid: string) =>
      api(`/opportunities/${id}/requirements/${rid}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Requirement removed.');
      refresh();
    },
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
  const mandatory = o.requirements.filter((r) => r.is_mandatory).length;

  const openAdd = () => {
    setEditingId(null);
    setReq(BLANK);
    setReqOpen(true);
  };
  const openEdit = (r: Requirement) => {
    setEditingId(r.id);
    setReq({
      factor: r.factor,
      description: r.description,
      is_mandatory: r.is_mandatory,
    });
    setReqOpen(true);
  };

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{o.title} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Opportunities', to: '/opportunities' },
          { label: o.title },
        ]}
        title={o.title}
        badges={<StatusBadge status={o.status} />}
        meta={
          <>
            <Link
              className="text-primary hover:underline"
              to={`/employers/${o.employer_id}`}
            >
              {o.employer}
            </Link>
            <span className="capitalize">{o.kind}</span>
            <span>
              {o.positions} position{o.positions === 1 ? '' : 's'}
            </span>
            <span>Closes {o.closing_date ?? 'not set'}</span>
          </>
        }
        actions={
          canEdit && (
            <>
              {!locked && (
                <Button variant="outline" onClick={() => setDateOpen(true)}>
                  <Pencil /> Set closing date
                </Button>
              )}
              {NEXT[o.status]?.map((n) => (
                <Button
                  key={n.to}
                  variant={n.to === 'closed' ? 'outline' : 'primary'}
                  disabled={move.isPending}
                  onClick={() =>
                    n.to === 'closed' ? setConfirmMove(n.to) : move.mutate(n.to)
                  }
                >
                  {n.label}
                </Button>
              ))}
            </>
          )
        }
      />
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Section title="Overview">
            <DetailList
              items={[
                { label: 'Status', value: <StatusBadge status={o.status} /> },
                {
                  label: 'Employer',
                  value: (
                    <Link
                      className="text-primary hover:underline"
                      to={`/employers/${o.employer_id}`}
                    >
                      {o.employer}
                    </Link>
                  ),
                },
                {
                  label: 'Type',
                  value: <span className="capitalize">{o.kind}</span>,
                },
                { label: 'Positions', value: o.positions },
                { label: 'Start date', value: o.start_date },
                { label: 'Closing date', value: o.closing_date },
                { label: 'Industry', value: o.sector },
                { label: 'County', value: o.county },
                { label: 'Location', value: o.location },
                { label: 'Description', value: o.description },
              ]}
            />
          </Section>

          <Section
            title="Requirements"
            description={`${o.requirements.length} in total, ${mandatory} mandatory. These feed opportunity compatibility.`}
            flush
            action={
              canEdit &&
              !locked && (
                <Button size="sm" onClick={openAdd}>
                  <Plus /> Add requirement
                </Button>
              )
            }
          >
            {o.requirements.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No requirements yet"
                  hint="Without requirements, compatibility cannot be assessed for this opportunity."
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead>Category</TableHead>
                      <TableHead>Requirement</TableHead>
                      <TableHead>Type</TableHead>
                      {canEdit && !locked && (
                        <TableHead className="w-24">
                          <span className="sr-only">Actions</span>
                        </TableHead>
                      )}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {o.requirements.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="capitalize">{r.factor}</TableCell>
                        <TableCell>{r.description}</TableCell>
                        <TableCell>
                          <Badge
                            variant={r.is_mandatory ? 'primary' : 'secondary'}
                            appearance="light"
                          >
                            {r.is_mandatory ? 'Mandatory' : 'Preferred'}
                          </Badge>
                        </TableCell>
                        {canEdit && !locked && (
                          <TableCell>
                            <div className="flex gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={`Edit ${r.description}`}
                                onClick={() => openEdit(r)}
                              >
                                <Pencil />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={`Remove ${r.description}`}
                                onClick={() => setRemoving(r)}
                              >
                                <Trash2 />
                              </Button>
                            </div>
                          </TableCell>
                        )}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </Section>
        </div>

        <Section title="Activity">
          {history.isPending ? (
            <LoadingState rows={3} />
          ) : (
            <ActivityTimeline events={history.data ?? []} />
          )}
        </Section>
      </div>

      <FormModal
        open={dateOpen}
        onOpenChange={setDateOpen}
        title="Set closing date"
        submitLabel="Save date"
        pending={setDate.isPending}
        onSubmit={() => setDate.mutate()}
      >
        <div className="space-y-1.5">
          <Label htmlFor="closing-date">
            Closing date <span className="text-destructive">*</span>
          </Label>
          <Input
            id="closing-date"
            type="date"
            required
            value={closing}
            onChange={(e) => setClosing(e.target.value)}
          />
        </div>
      </FormModal>

      <FormModal
        open={reqOpen}
        onOpenChange={setReqOpen}
        title={editingId ? 'Edit requirement' : 'Add requirement'}
        description="Requirements are checked against participants when compatibility is assessed."
        submitLabel={editingId ? 'Save changes' : 'Add requirement'}
        pending={saveReq.isPending}
        onSubmit={() => saveReq.mutate()}
      >
        <div className="space-y-1.5">
          <Label>Category</Label>
          <Select
            value={req.factor}
            onValueChange={(v) => setReq({ ...req, factor: v })}
          >
            <SelectTrigger aria-label="Category" className="capitalize">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FACTORS.map((f) => (
                <SelectItem key={f} value={f} className="capitalize">
                  {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="req-description">
            Requirement <span className="text-destructive">*</span>
          </Label>
          <Input
            id="req-description"
            required
            maxLength={300}
            value={req.description}
            onChange={(e) => setReq({ ...req, description: e.target.value })}
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={req.is_mandatory}
            onChange={(e) => setReq({ ...req, is_mandatory: e.target.checked })}
          />
          Mandatory (otherwise preferred)
        </label>
      </FormModal>

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(x) => !x && setRemoving(null)}
        title="Remove this requirement?"
        description="It will no longer count towards compatibility. The removal is kept in the activity history."
        onConfirm={() => removing && delReq.mutate(removing.id)}
      />
      <ConfirmDialog
        open={confirmMove !== null}
        onOpenChange={(x) => !x && setConfirmMove(null)}
        title="Close this opportunity?"
        description="Its status becomes closed. You can reopen it later."
        confirmLabel="Close opportunity"
        onConfirm={() => confirmMove && move.mutate(confirmMove)}
      />
    </div>
  );
}
