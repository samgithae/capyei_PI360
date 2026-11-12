import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { ReferDialog } from '@/pages/referrals/referral-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Send, Trash2 } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
import { EditOpportunity } from './opportunity-edit';
import { RequirementForm } from './requirement-form';
import {
  BLANK,
  categoryLabel,
  summary,
  toDraft,
  toPayload,
  type Draft,
  type Lookup,
  type Req,
} from './requirement-model';
import { SuggestedYouth } from './suggested-youth';

interface Requirement extends Req {
  id: string;
  needs_structuring: boolean;
}
interface Opt {
  id: string;
  name: string;
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
  requirement_options: {
    levels: Opt[];
    grades: (Opt & { level_id: string; rank: number })[];
    skills: Opt[];
    work_patterns: Opt[];
  };
}
interface Event {
  at: string;
  actor: string;
  action: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
}

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
  const [dateOpen, setDateOpen] = useState(false);
  const [closing, setClosing] = useState('');
  const [reqOpen, setReqOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [req, setReq] = useState<Draft>(BLANK);
  const [reqError, setReqError] = useState('');
  const [removing, setRemoving] = useState<Requirement | null>(null);
  const [confirmMove, setConfirmMove] = useState<string | null>(null);
  const [referring, setReferring] = useState(false);
  const [editingDetails, setEditingDetails] = useState(false);

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
  const ro = q.data?.requirement_options;
  const lookup: Lookup = {
    levels: ro?.levels ?? [],
    grades: ro?.grades ?? [],
    skills: ro?.skills ?? [],
    patterns: ro?.work_patterns ?? [],
  };
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
            body: JSON.stringify(toPayload(req, lookup)),
          })
        : post(`/opportunities/${id}/requirements`, toPayload(req, lookup)),
    onSuccess: () => {
      toast.success(editingId ? 'Requirement updated.' : 'Requirement added.');
      setReqOpen(false);
      setReq(BLANK);
      setEditingId(null);
      refresh();
    },
    onError: (e) =>
      setReqError(e instanceof ApiError ? e.message : 'Could not save.'),
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
    setReqError('');
    setReqOpen(true);
  };
  const openEdit = (r: Requirement) => {
    setEditingId(r.id);
    setReq(toDraft(r));
    setReqError('');
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
          <>
            {can('referrals.edit') && o.status === 'open' && (
              <Button variant="outline" onClick={() => setReferring(true)}>
                <Send /> Refer youth
              </Button>
            )}
            {canEdit && (
              <>
                {!locked && (
                  <Button
                    variant="outline"
                    onClick={() => setEditingDetails(true)}
                  >
                    <Pencil /> Edit details
                  </Button>
                )}
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
                      n.to === 'closed'
                        ? setConfirmMove(n.to)
                        : move.mutate(n.to)
                    }
                  >
                    {n.label}
                  </Button>
                ))}
              </>
            )}
          </>
        }
      />
      {editingDetails && (
        <EditOpportunity id={o.id} onClose={() => setEditingDetails(false)} />
      )}
      <ReferDialog
        open={referring}
        onOpenChange={setReferring}
        opportunity={{ id: o.id, name: `${o.title} (${o.employer})` }}
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
                      <TableHead>Requirement</TableHead>
                      <TableHead>Category</TableHead>
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
                        <TableCell>
                          <span className="font-medium">
                            {summary(r, lookup).name}
                          </span>
                          {summary(r, lookup).extras.map((x) => (
                            <span
                              key={x}
                              className="ms-2 text-xs text-muted-foreground"
                            >
                              {x}
                            </span>
                          ))}
                          {r.needs_structuring && (
                            <Badge
                              className="ms-2"
                              variant="warning"
                              appearance="light"
                              size="sm"
                            >
                              Needs structuring
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell>{categoryLabel(r)}</TableCell>
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
                                aria-label={`Edit ${summary(r, lookup).name}`}
                                onClick={() => openEdit(r)}
                              >
                                <Pencil />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={`Remove ${summary(r, lookup).name}`}
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

        {can('participants.view_profile') && (
          <SuggestedYouth
            id={o.id}
            positions={o.positions}
            canRefer={can('referrals.edit') && o.status === 'open'}
          />
        )}

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

      <RequirementForm
        open={reqOpen}
        onOpenChange={setReqOpen}
        editing={editingId !== null}
        draft={req}
        onChange={setReq}
        lookup={lookup}
        canAddSkill={can('reference.manage')}
        onCatalogueChanged={() =>
          void qc.invalidateQueries({ queryKey: ['opportunity', id] })
        }
        pending={saveReq.isPending}
        error={reqError}
        onSubmit={() => {
          setReqError('');
          saveReq.mutate();
        }}
      />

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
