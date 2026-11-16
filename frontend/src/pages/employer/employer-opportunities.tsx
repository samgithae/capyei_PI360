import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { WhereWhatFields } from '@/pages/opportunities/opportunity-fields';
import { RequirementForm } from '@/pages/opportunities/requirement-form';
import {
  BLANK,
  categoryLabel,
  summary,
  toDraft,
  toPayload,
  type Draft,
  type Lookup,
  type Req,
} from '@/pages/opportunities/requirement-model';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
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
import {
  DataCard,
  FilterSelect,
  Pager,
  SearchBox,
} from '@/components/data-card';
import { DetailList, Section } from '@/components/shared/info-card';
import { ConfirmDialog, FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
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
import {
  OPPORTUNITY_VIEW_LABELS,
  type OpportunityPage,
  type OpportunityRow,
} from './employer-types';
import { useEmployerMe } from './use-employer';

const KINDS = ['job', 'internship', 'apprenticeship', 'other'];
const STATUSES = ['draft', 'open', 'closed', 'expired'];
const PLACES = '/employer/profile';
const PROFILE = '/employer/company';

interface Requirement extends Req {
  id: string;
  needs_structuring: boolean;
}
interface Opt {
  id: string;
  name: string;
}
interface Detail extends OpportunityRow {
  sector_ids: string[];
  county_ids: string[];
  location: string;
  description: string;
  start_date: string | null;
  publishes_directly: boolean;
  requirements: Requirement[];
  requirement_options: {
    levels: Opt[];
    grades: (Opt & { level_id: string; rank: number })[];
    skills: Opt[];
    work_patterns: Opt[];
  };
}

/** What a company's list or figure should refresh after any change. */
function useRefresh(id?: string) {
  const qc = useQueryClient();
  return () => {
    if (id)
      void qc.invalidateQueries({ queryKey: ['employer-opportunity', id] });
    void qc.invalidateQueries({ queryKey: ['employer-opportunities'] });
    void qc.invalidateQueries({ queryKey: ['employer-dashboard'] });
  };
}

interface Form {
  title: string;
  kind: string;
  positions: string;
  sector_ids: string[];
  county_ids: string[];
  location: string;
  description: string;
  start_date: string | null;
  closing_date: string | null;
}

const NEW: Form = {
  title: '',
  kind: 'job',
  positions: '1',
  sector_ids: [],
  county_ids: [],
  location: '',
  description: '',
  start_date: null,
  closing_date: null,
};

/** Add (no `existing`) or edit (an opportunity) in one dialog, so the two cannot drift apart. */
function OpportunityDialog({
  open,
  onOpenChange,
  existing,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existing?: Detail;
}) {
  const nav = useNavigate();
  const refresh = useRefresh(existing?.id);
  const me = useEmployerMe();
  const [v, setV] = useState<Form>(NEW);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!open) return;
    setError('');
    setV(
      existing
        ? {
            title: existing.title,
            kind: existing.kind,
            positions: String(existing.positions),
            sector_ids: existing.sector_ids,
            county_ids: existing.county_ids,
            location: existing.location,
            description: existing.description,
            start_date: existing.start_date,
            closing_date: existing.closing_date,
          }
        : NEW,
    );
  }, [open, existing]);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...v,
        positions: Number(v.positions),
        start_date: v.start_date || null,
        closing_date: v.closing_date || null,
      };
      return existing
        ? api<Detail>(`/employer/opportunities/${existing.id}`, {
            method: 'PATCH',
            body: JSON.stringify(body),
          })
        : post<Detail>('/employer/opportunities', body);
    },
    onSuccess: (o) => {
      refresh();
      onOpenChange(false);
      if (existing) toast.success('Opportunity updated.');
      else {
        toast.success('Saved as a draft. Choose its skills next.');
        nav(`/employer/opportunities/${o.id}?skills=1`);
      }
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title={existing ? 'Edit opportunity' : 'Add opportunity'}
      description={
        existing
          ? undefined
          : 'It is saved as a draft. Next you choose its skills, then open it.'
      }
      submitLabel={existing ? 'Save changes' : 'Save as draft'}
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!v.title.trim()) return setError('Enter a title.');
        setError('');
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="eo-title">
          Title <span className="text-destructive">*</span>
        </Label>
        <Input
          id="eo-title"
          required
          value={v.title}
          onChange={(e) => setV({ ...v, title: e.target.value })}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Type</Label>
          <SelectField
            label="Type"
            value={v.kind}
            options={KINDS.map((k) => ({ id: k, name: k }))}
            onChange={(x) => setV({ ...v, kind: x })}
            className="capitalize"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="eo-positions">Positions</Label>
          <Input
            id="eo-positions"
            type="number"
            min={1}
            value={v.positions}
            onChange={(e) => setV({ ...v, positions: e.target.value })}
          />
        </div>
      </div>
      <WhereWhatFields
        idPrefix="eo"
        employerId={me.data?.employer.id ?? ''}
        placesPath={PLACES}
        profileHref={PROFILE}
        value={v}
        onChange={(p) => setV((x) => ({ ...x, ...p }))}
      />
    </FormModal>
  );
}

export function EmployerOpportunitiesPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const q = useQuery({
    queryKey: ['employer-opportunities', params.toString()],
    queryFn: () =>
      api<OpportunityPage>(`/employer/opportunities?${params.toString()}`),
  });
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const data = q.data;
  const view = params.get('view') ?? '';
  const offset = Number(params.get('offset') ?? 0);
  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Opportunities | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Opportunities' }]}
        title="Opportunities"
        description="The jobs, internships and apprenticeships your company offers."
        actions={
          can('employer.edit_opportunities') && (
            <Button onClick={() => setAdding(true)}>
              <Plus /> Add opportunity
            </Button>
          )
        }
      />
      {view && OPPORTUNITY_VIEW_LABELS[view] && (
        <Notice title={`Showing: ${OPPORTUNITY_VIEW_LABELS[view]}`}>
          <button
            type="button"
            className="text-primary underline"
            onClick={() => set('view', '')}
          >
            Show all opportunities
          </button>
        </Notice>
      )}
      <OpportunityDialog open={adding} onOpenChange={setAdding} />
      <DataCard
        footer={
          data && data.total > 0 ? (
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
          </>
        }
      >
        {q.isError && (
          <div className="p-5">
            <ErrorState error={q.error} onRetry={() => void q.refetch()} />
          </div>
        )}
        {q.isPending && (
          <div className="p-5">
            <LoadingState />
          </div>
        )}
        {data && data.results.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Title</TableHead>
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
                      to={`/employer/opportunities/${o.id}`}
                    >
                      {o.title}
                    </Link>
                  </TableCell>
                  <TableCell className="capitalize">{o.kind}</TableCell>
                  <TableCell>{o.positions}</TableCell>
                  <TableCell>{o.closing_date ?? ''}</TableCell>
                  <TableCell className="space-x-2">
                    <StatusBadge status={o.status} />
                    {o.publish_request.state === 'pending' && (
                      <Badge variant="warning" appearance="light">
                        Awaiting approval
                      </Badge>
                    )}
                    {o.publish_request.state === 'declined' && (
                      <Badge variant="destructive" appearance="light">
                        Sent back
                      </Badge>
                    )}
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

export function EmployerOpportunityPage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const { can } = useAuth();
  const refresh = useRefresh(id);
  const canEdit = can('employer.edit_opportunities');
  const canPublish = can('employer.publish_opportunities');
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [reqOpen, setReqOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [req, setReq] = useState<Draft>(BLANK);
  const [reqError, setReqError] = useState('');
  const [removing, setRemoving] = useState<Requirement | null>(null);
  const [closing, setClosing] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [skillsError, setSkillsError] = useState('');

  const fail = (e: unknown) => {
    const m = e instanceof ApiError ? e.message : 'Something went wrong.';
    setError(m);
    toast.error(m);
  };
  const q = useQuery({
    queryKey: ['employer-opportunity', id],
    queryFn: () => api<Detail>(`/employer/opportunities/${id}`),
    retry: false,
  });
  const o = q.data;
  const locked = o?.status === 'closed' || o?.status === 'expired';
  // A new draft arrives with ?skills=1 so the picker opens straight away.
  useEffect(() => {
    if (params.get('skills') && o && !locked && canEdit) {
      setSkillsOpen(true);
      setParams({}, { replace: true });
    }
  }, [params, o, locked, canEdit, setParams]);

  const ro = o?.requirement_options;
  const lookup: Lookup = {
    levels: ro?.levels ?? [],
    grades: ro?.grades ?? [],
    skills: ro?.skills ?? [],
    patterns: ro?.work_patterns ?? [],
  };
  const base = `/employer/opportunities/${id}`;
  const move = useMutation({
    mutationFn: (to: string) => post<Detail>(`${base}/transition`, { to }),
    onSuccess: (d, to) => {
      setError('');
      toast.success(
        to === 'withdraw'
          ? 'Request withdrawn.'
          : to === 'closed'
            ? 'Opportunity closed.'
            : d.publish_request.state === 'pending'
              ? 'Sent to PI 360 for approval.'
              : 'Opportunity is now open.',
      );
      refresh();
    },
    onError: fail,
  });
  const saveReq = useMutation({
    mutationFn: () =>
      editingId
        ? api(`${base}/requirements/${editingId}`, {
            method: 'PATCH',
            body: JSON.stringify(toPayload(req, lookup)),
          })
        : post(`${base}/requirements`, toPayload(req, lookup)),
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
  const saveSkills = useMutation({
    mutationFn: (picked: PickedSkill[]) =>
      api(`${base}/requirements/skills`, {
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
      api(`${base}/requirements/${rid}`, { method: 'DELETE' }),
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
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        )}
        <Link className="text-primary" to="/employer/opportunities">
          Back to opportunities
        </Link>
      </div>
    );
  }
  if (!o) return <LoadingState />;
  const pr = o.publish_request;
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
  const reopen = o.status === 'closed' || o.status === 'expired';
  const openLabel = o.publishes_directly
    ? reopen
      ? 'Reopen'
      : 'Open'
    : reopen
      ? 'Ask to reopen'
      : 'Send for approval';

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{o.title} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Opportunities', to: '/employer/opportunities' },
          { label: o.title },
        ]}
        title={o.title}
        badges={<StatusBadge status={o.status} />}
        meta={
          <>
            <span className="capitalize">{o.kind}</span>
            <span>
              {o.positions} position{o.positions === 1 ? '' : 's'}
            </span>
            <span>Closes {o.closing_date ?? 'not set'}</span>
          </>
        }
        actions={
          <>
            {o.status === 'open' && (
              <Button variant="outline" asChild>
                <Link to={`/employer/referrals?opportunity=${o.id}`}>
                  View referrals
                </Link>
              </Button>
            )}
            {canEdit && !locked && (
              <Button variant="outline" onClick={() => setEditing(true)}>
                <Pencil /> Edit details
              </Button>
            )}
            {canPublish && pr.state === 'pending' && (
              <Button
                variant="outline"
                disabled={move.isPending}
                onClick={() => move.mutate('withdraw')}
              >
                Withdraw request
              </Button>
            )}
            {canPublish && o.status === 'open' && (
              <Button variant="outline" onClick={() => setClosing(true)}>
                Close
              </Button>
            )}
            {canPublish && o.status !== 'open' && pr.state !== 'pending' && (
              <Button
                disabled={move.isPending}
                onClick={() => move.mutate('open')}
              >
                {openLabel}
              </Button>
            )}
          </>
        }
      />
      {pr.state === 'pending' && (
        <Notice tone="info" title="Waiting for PI 360 to approve this">
          Sent{pr.requested_by ? ` by ${pr.requested_by}` : ''}
          {pr.requested_at
            ? ` on ${new Date(pr.requested_at).toLocaleDateString()}`
            : ''}
          . It opens as soon as PI 360 approves it. You can withdraw it and keep
          editing.
        </Notice>
      )}
      {pr.state === 'declined' && (
        <Notice tone="warning" title="PI 360 sent this back">
          {pr.declined_reason || 'No reason was given.'} Make the changes, then
          send it again.
        </Notice>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <OpportunityDialog
        open={editing}
        onOpenChange={setEditing}
        existing={o}
      />

      <Section title="Overview">
        <DetailList
          items={[
            { label: 'Status', value: <StatusBadge status={o.status} /> },
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
        description={`${o.requirements.length} in total, ${mandatory} mandatory. PI 360 uses these to suggest suitable young people.`}
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
              hint="Without requirements, PI 360 cannot suggest young people for this opportunity."
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
        endpoint="/employer/skills"
        initial={o.requirements
          .filter((r) => r.factor === 'skill' && r.skill_id)
          .map((r) => ({
            id: r.skill_id as string,
            name:
              lookup.skills.find((s) => s.id === r.skill_id)?.name ??
              r.description,
            mandatory: r.is_mandatory,
          }))}
        canAdd={false}
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
        description="PI 360 will no longer use it to suggest young people."
        onConfirm={() => removing && delReq.mutate(removing.id)}
      />
      <ConfirmDialog
        open={closing}
        onOpenChange={setClosing}
        title="Close this opportunity?"
        description="PI 360 will stop referring young people to it. You can reopen it later."
        confirmLabel="Close opportunity"
        onConfirm={() => move.mutate('closed')}
      />
    </div>
  );
}
