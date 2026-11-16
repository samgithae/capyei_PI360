import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { ReferDialog } from '@/pages/referrals/referral-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Send, Trash2 } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useParams, useSearchParams } from 'react-router';
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
import {
  SkillPickerDialog,
  type PickedSkill,
} from '@/components/shared/skill-picker';
import { StatusBadge } from '@/components/shared/status-badge';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
} from '@/components/states';
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
  publish_request?: {
    state: 'none' | 'pending' | 'declined';
    requested_by: string;
    declined_reason: string;
  };
  sectors: { id: string; name: string }[];
  counties: { id: string; name: string }[];
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
  const [params, setParams] = useSearchParams();
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
  const [declining, setDeclining] = useState(false);
  const [declineReason, setDeclineReason] = useState('');
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [skillsError, setSkillsError] = useState('');
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
  // A new draft arrives with ?skills=1 so the picker opens straight away.
  const ready =
    q.data && q.data.status !== 'closed' && q.data.status !== 'expired';
  useEffect(() => {
    if (params.get('skills') && ready && canEdit) {
      setSkillsOpen(true);
      setParams({}, { replace: true });
    }
  }, [params, ready, canEdit, setParams]);
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
  const decline = useMutation({
    mutationFn: () =>
      post(`/opportunities/${id}/publish-decline`, { reason: declineReason }),
    onSuccess: () => {
      toast.success('Sent back to the company.');
      setDeclining(false);
      setDeclineReason('');
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
  // The skills picker saves every skill requirement in one call.
  const saveSkills = useMutation({
    mutationFn: (picked: PickedSkill[]) =>
      api(`/opportunities/${id}/requirements/skills`, {
        method: 'PUT',
        body: JSON.stringify({
          skills: picked.map((p) => ({
            skill_id: p.id,
            is_mandatory: p.mandatory,
          })),
        }),
      }),
    onSuccess: () => {
      toast.success('Skills saved.');
      setSkillsOpen(false);
      refresh();
    },
    onError: (e) =>
      setSkillsError(e instanceof ApiError ? e.message : 'Could not save.'),
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
  const openSkills = () => {
    setSkillsError('');
    setReqOpen(false);
    setSkillsOpen(true);
  };
  const openEdit = (r: Requirement) => {
    if (r.factor === 'skill' && r.skill_id) return openSkills();
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

      {o.publish_request?.state === 'pending' && (
        <Notice tone="warning" title="Waiting for your approval">
          <p>
            {o.employer} asked to publish this opportunity
            {o.publish_request.requested_by
              ? ` (${o.publish_request.requested_by})`
              : ''}
            . Opening it makes it available for referrals.
          </p>
          {canEdit && (
            <div className="mt-3 flex gap-2">
              <Button
                size="sm"
                disabled={move.isPending}
                onClick={() => move.mutate('open')}
              >
                Approve and open
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setDeclining(true)}
              >
                Send back with a reason
              </Button>
            </div>
          )}
        </Notice>
      )}
      {o.publish_request?.state === 'declined' && (
        <Notice tone="info" title="Sent back to the company">
          <p>Reason shown to them: {o.publish_request.declined_reason}</p>
        </Notice>
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
                {
                  label: 'Industry / Sector',
                  value: o.sectors.map((x) => x.name).join(', '),
                },
                {
                  label: 'Counties',
                  value: o.counties.map((x) => x.name).join(', '),
                },
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
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={openSkills}>
                    <Plus /> Choose skills
                  </Button>
                  <Button size="sm" onClick={openAdd}>
                    <Plus /> Add requirement
                  </Button>
                </div>
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
        onPickSkills={openSkills}
        pending={saveReq.isPending}
        error={reqError}
        onSubmit={() => {
          setReqError('');
          saveReq.mutate();
        }}
      />

      <SkillPickerDialog
        open={skillsOpen}
        onOpenChange={setSkillsOpen}
        resetKey={o.id}
        initial={o.requirements
          .filter((r) => r.factor === 'skill' && r.skill_id)
          .map((r) => ({
            id: r.skill_id as string,
            name:
              lookup.skills.find((s) => s.id === r.skill_id)?.name ??
              r.description,
            mandatory: r.is_mandatory,
          }))}
        canAdd={canEdit}
        saving={saveSkills.isPending}
        error={skillsError}
        onSave={(picked) => {
          setSkillsError('');
          saveSkills.mutate(picked);
        }}
      />

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(x) => !x && setRemoving(null)}
        title="Remove this requirement?"
        description="It will no longer count towards compatibility. The removal is kept in the activity history."
        onConfirm={() => removing && delReq.mutate(removing.id)}
      />
      <FormModal
        open={declining}
        onOpenChange={setDeclining}
        title="Send back to the company"
        description="The company sees this reason on the opportunity and can fix it and ask again."
        submitLabel="Send back"
        pending={decline.isPending}
        error={error}
        onSubmit={() => {
          if (!declineReason.trim()) return;
          decline.mutate();
        }}
      >
        <Label htmlFor="decline-reason">Reason</Label>
        <Input
          id="decline-reason"
          maxLength={500}
          value={declineReason}
          onChange={(e) => setDeclineReason(e.target.value)}
        />
      </FormModal>
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
