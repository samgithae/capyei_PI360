import { useState } from 'react';
import type { FollowUpRow } from '@/pages/followups/followup-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';

// Shapes returned by /api/v1/interventions, /cases/queue and /placements
// (backend: apps/referrals/case_views.py and apps/casework/views.py).
export interface InterventionRow {
  id: string;
  participant_id: string;
  participant: string;
  need: string;
  need_label: string;
  title: string;
  status: string;
  status_label: string;
  owner: string;
  owner_id: number | null;
  due_date: string | null;
  overdue: boolean;
  follow_up_of_id: string | null;
  closed_at: string | null;
  updated_at: string;
}
export interface InterventionPage {
  total: number;
  page_size: number;
  results: InterventionRow[];
}
export interface InterventionDetail extends InterventionRow {
  detail: string;
  verification_source: string;
  verification_source_label: string;
  outcome_note: string;
  created_by: string;
  created_at: string;
  next_statuses: string[];
  follow_ups: { id: string; title: string; status_label: string }[];
  can: { edit: boolean; reassign: boolean; follow_up: boolean };
}
export interface Option {
  value: string;
  label: string;
}
export interface CaseOptions {
  needs: Option[];
  sources: Option[];
  statuses: Option[];
}
export interface PlacementRow {
  id: string;
  participant_id: string;
  participant: string;
  enrollment_id: string;
  employer_id: string | null;
  employer: string;
  linked: boolean;
  designation: string;
  pathway: string;
  pathway_label: string;
  status: string;
  source_status: string;
  start_date: string | null;
  end_date: string | null;
  exit_reason: string;
  current: boolean;
  verified: boolean;
  verified_on: string | null;
  verification_source: string;
  verification_source_label: string;
  imported: boolean;
  // Self-employment outcome (NEW-071); blank on every other pathway.
  business_activity: string;
  operational_status: string;
  operational_status_label: string;
  business_evidence: string;
  // Employment type (NEW-035, B25); blank when not recorded.
  employment_type_id: string | null;
  employment_type: string;
}
export interface PlacementDetail extends PlacementRow {
  benefits: string;
  /** Only for holders of the restricted economic-data grant; otherwise null. */
  monthly_income: string | null;
  /** Salary and band (A3): restricted economic data, like income. */
  salary_amount: string | null;
  salary_band_id: string | null;
  salary_band: string;
  can: { edit: boolean; end: boolean; verify: boolean; income: boolean };
}
export interface PlacementPage {
  total: number;
  page_size: number;
  results: PlacementRow[];
}
export interface PlacementSummary {
  total: number;
  current: number;
  ended: number;
  unverified: number;
  by_pathway: Record<string, { label: string; current: number }>;
}
export interface PlacementOptions {
  pathways: Option[];
  sources: Option[];
  operational_statuses: Option[];
  /** CAP-YEI has not confirmed the operational status list yet. */
  operational_statuses_provisional: boolean;
  can_record_income: boolean;
  /** NEW-035. Salary bands are listed only to those who may record a salary. */
  employment_types: EmploymentType[];
  salary_bands: SalaryBand[];
}
export interface EmploymentType {
  id: string;
  name: string;
  self_employment: boolean;
}
export interface SalaryBand {
  id: string;
  name: string;
  min_amount: string | null;
  max_amount: string | null;
}

export const SELF_EMPLOYMENT = 'self_employment';

/** The self-employment outcome's own facts (D-080 / B27). */
export interface BusinessState {
  activity: string;
  status: string;
  evidence: string;
  income: string;
}

export function emptyBusiness(row?: PlacementRow): BusinessState {
  return {
    activity: row?.business_activity ?? '',
    status: row?.operational_status ?? '',
    evidence: row?.business_evidence ?? '',
    income: '',
  };
}

/** Request fields for the business details: blank unless the pathway is self-employment, and
 * income only when typed (the server refuses it without the restricted grant). */
export function businessBody(pathway: string, b: BusinessState) {
  if (pathway !== SELF_EMPLOYMENT)
    return {
      business_activity: '',
      operational_status: '',
      business_evidence: '',
    };
  return {
    business_activity: b.activity,
    operational_status: b.status,
    business_evidence: b.evidence,
    ...(b.income.trim() ? { monthly_income: b.income.trim() } : {}),
  };
}

export function BusinessFields({
  id,
  value,
  onChange,
  options,
}: {
  id: string;
  value: BusinessState;
  onChange: (next: BusinessState) => void;
  options?: PlacementOptions;
}) {
  const set = (k: keyof BusinessState) => (v: string) =>
    onChange({ ...value, [k]: v });
  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      <legend className="px-1 text-sm font-medium">Business details</legend>
      <p className="text-xs text-muted-foreground">
        Self-employment is its own outcome, never counted as formal employment.
        Put the business name in the employer or business name field above.
      </p>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-activity`}>Business activity</Label>
        <Input
          id={`${id}-activity`}
          maxLength={200}
          value={value.activity}
          onChange={(e) => set('activity')(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label>Operational status</Label>
        <SelectField
          label="Choose operational status"
          value={value.status}
          options={asOptions(options?.operational_statuses)}
          onChange={set('status')}
        />
        {options?.operational_statuses_provisional && (
          <p className="text-xs text-muted-foreground">
            Working list, waiting for CAP-YEI to confirm.
          </p>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-evidence`}>Evidence of business activity</Label>
        <Textarea
          id={`${id}-evidence`}
          maxLength={2000}
          value={value.evidence}
          onChange={(e) => set('evidence')(e.target.value)}
        />
      </div>
      {options?.can_record_income && (
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-income`}>
            Monthly income (KES, where available)
          </Label>
          <Input
            id={`${id}-income`}
            inputMode="decimal"
            value={value.income}
            onChange={(e) => set('income')(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Restricted economic data: only staff with the grant see it.
          </p>
        </div>
      )}
    </fieldset>
  );
}
/** Employment type, salary and band (NEW-035, B25, A3). */
export interface WorkState {
  type: string;
  amount: string;
  band: string;
  /** Salary fields are sent only once touched, so a form opened from a list row (which does
   * not carry the salary) never clears one already recorded. */
  salaryTouched: boolean;
}

export function emptyWork(row?: PlacementRow | PlacementDetail): WorkState {
  const detail = row as Partial<PlacementDetail> | undefined;
  return {
    type: row?.employment_type_id ?? '',
    amount: detail?.salary_amount ?? '',
    band: detail?.salary_band_id ?? '',
    salaryTouched: false,
  };
}

/** The types that fit the pathway: the self-employment type with self-employment only. */
export function typesFor(pathway: string, options?: PlacementOptions) {
  return (options?.employment_types ?? []).filter(
    (t) => t.self_employment === (pathway === SELF_EMPLOYMENT),
  );
}

export function workBody(
  pathway: string,
  w: WorkState,
  options?: PlacementOptions,
) {
  const fits = typesFor(pathway, options).some((t) => t.id === w.type);
  const body: Record<string, string | null> = {
    employment_type_id: fits ? w.type : null,
  };
  if (
    options?.can_record_income &&
    pathway !== SELF_EMPLOYMENT &&
    w.salaryTouched
  ) {
    body.salary_amount = w.amount.trim() || null;
    body.salary_band_id = w.band || null;
  }
  return body;
}

export function WorkFields({
  id,
  pathway,
  value,
  onChange,
  options,
}: {
  id: string;
  pathway: string;
  value: WorkState;
  onChange: (next: WorkState) => void;
  options?: PlacementOptions;
}) {
  const types = typesFor(pathway, options);
  const paid = pathway !== SELF_EMPLOYMENT;
  return (
    <>
      <div className="space-y-1.5">
        <Label>Employment type</Label>
        <SelectField
          label="Choose employment type"
          value={types.some((t) => t.id === value.type) ? value.type : ''}
          options={types.map((t) => ({ id: t.id, name: t.name }))}
          onChange={(type) => onChange({ ...value, type })}
        />
      </div>
      {paid && options?.can_record_income && (
        <fieldset className="space-y-3 rounded-md border p-3">
          <legend className="px-1 text-sm font-medium">Salary</legend>
          <p className="text-xs text-muted-foreground">
            Restricted economic data: only staff with the grant see it. Give the
            exact monthly amount, or only a band if that is all that is known.
          </p>
          <div className="space-y-1.5">
            <Label htmlFor={`${id}-salary`}>Monthly salary (KES)</Label>
            <Input
              id={`${id}-salary`}
              inputMode="decimal"
              value={value.amount}
              onChange={(e) =>
                onChange({
                  ...value,
                  amount: e.target.value,
                  band: '',
                  salaryTouched: true,
                })
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label>Salary band</Label>
            <SelectField
              label="Choose salary band"
              value={value.band}
              options={(options.salary_bands ?? []).map((b) => ({
                id: b.id,
                name: b.name,
              }))}
              onChange={(band) =>
                onChange({ ...value, band, salaryTouched: true })
              }
            />
            <p className="text-xs text-muted-foreground">
              {options.salary_bands?.length
                ? 'Left empty, the band is found from the amount.'
                : 'No bands are set up yet: an administrator adds them under Administration.'}
            </p>
          </div>
        </fieldset>
      )}
    </>
  );
}

export interface QueueData {
  scope: 'mine' | 'all';
  today: string;
  counts: {
    live: number;
    overdue: number;
    due_soon: number;
    awaiting_verification: number;
    referrals_waiting: number;
    flagged?: number;
    placements_to_verify?: number;
    followups_open?: number;
    followups_overdue?: number;
    followups_due_soon?: number;
  };
  interventions: {
    id: string;
    participant_id: string;
    participant: string;
    need_label: string;
    title: string;
    status: string;
    status_label: string;
    owner: string;
    due_date: string | null;
    overdue: boolean;
  }[];
  referrals: {
    id: string;
    participant_id: string;
    participant: string;
    opportunity: string;
    employer: string;
    stage: string;
    stage_label: string;
    assigned_to: string;
    days_waiting: number;
  }[];
  flags: {
    total: number;
    items: {
      participant_id: string;
      name: string;
      flags: { code: string; label: string; detail: string }[];
    }[];
  } | null;
  placements_to_verify: number | null;
  followups: FollowUpRow[] | null;
}

export const asOptions = (o: Option[] | undefined) =>
  (o ?? []).map((x) => ({ id: x.value, name: x.label }));

/** Kinds of support, statuses and verification sources for the intervention forms. */
export function useCaseOptions(enabled = true) {
  return useQuery({
    queryKey: ['intervention-options'],
    queryFn: () => api<CaseOptions>('/interventions/options'),
    enabled,
    staleTime: 5 * 60_000,
  });
}

/** Pathways and verification sources for the placement forms. */
export function usePlacementOptions(enabled = true) {
  return useQuery({
    queryKey: ['placement-options'],
    queryFn: () => api<PlacementOptions>('/placements/options'),
    enabled,
    staleTime: 5 * 60_000,
  });
}

/** Every query a case or placement change can make stale, so lists and counts refresh. */
export function useRefreshCases() {
  const qc = useQueryClient();
  return () => {
    for (const key of [
      'case-queue',
      'interventions',
      'intervention',
      'intervention-history',
      'placements',
      'placement-summary',
      'placement-history',
      'followups',
      'followup',
      'followup-summary',
      'followup-history',
    ])
      void qc.invalidateQueries({ queryKey: [key] });
  };
}

export const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : 'Could not save.';

export const Required = () => <span className="text-destructive"> *</span>;

/** Pick a youth by searching their name (the list is scoped by the server). */
function YouthPicker({
  value,
  onChange,
  open,
}: {
  value: string;
  onChange: (id: string) => void;
  open: boolean;
}) {
  const [q, setQ] = useState('');
  const youth = useQuery({
    queryKey: ['case-youth', q],
    queryFn: () =>
      api<{ results: { id: string; name: string }[] }>(
        `/participants?q=${encodeURIComponent(q)}`,
      ),
    enabled: open,
  });
  return (
    <div className="space-y-1.5">
      <Label htmlFor="case-youth">
        Youth
        <Required />
      </Label>
      <Input
        id="case-youth"
        placeholder="Search youth by name"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <SelectField
        label="Choose youth"
        value={value}
        options={youth.data?.results ?? []}
        onChange={onChange}
      />
    </div>
  );
}

/** Pick an employer by searching (optional; leave empty to type a name instead). */
function EmployerPicker({
  value,
  onChange,
  open,
  known,
}: {
  value: string;
  onChange: (id: string) => void;
  open: boolean;
  /** An employer already chosen elsewhere (e.g. from a referral); kept in the list so it
   * still shows when the search results do not include it. */
  known?: { id: string; name: string };
}) {
  const [q, setQ] = useState('');
  const list = useQuery({
    queryKey: ['case-employers', q],
    queryFn: () =>
      api<{ results: { id: string; name: string }[] }>(
        `/employers?q=${encodeURIComponent(q)}`,
      ),
    enabled: open,
  });
  return (
    <div className="space-y-1.5">
      <Label htmlFor="case-employer">Employer on the register</Label>
      <Input
        id="case-employer"
        placeholder="Search employers by name"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <SelectField
        label="Choose employer"
        value={value}
        emptyLabel="Not on the register"
        options={withKnown(list.data?.results ?? [], known)}
        onChange={onChange}
      />
    </div>
  );
}

function withKnown(
  options: { id: string; name: string }[],
  known?: { id: string; name: string },
) {
  return known && !options.some((o) => o.id === known.id)
    ? [known, ...options]
    : options;
}

/** Staff who work cases, for assigning an owner (needs caseload.reassign). */
export function useOwners(enabled: boolean) {
  return useQuery({
    queryKey: ['referral-assignees'],
    queryFn: () => api<{ id: number; name: string }[]>('/referrals/assignees'),
    enabled,
  });
}

/** Create an intervention, a follow-up to one, or edit a live one. */
export function InterventionDialog({
  open,
  onOpenChange,
  participant,
  followUpOf,
  edit,
  canAssign,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  participant?: { id: string; name: string };
  followUpOf?: { id: string; participant: string; title: string };
  edit?: InterventionDetail;
  canAssign?: boolean;
  onSaved?: (id: string) => void;
}) {
  const refresh = useRefreshCases();
  const options = useCaseOptions(open);
  const owners = useOwners(open && !!canAssign && !edit);
  const [youthId, setYouthId] = useState('');
  const [need, setNeed] = useState(edit?.need ?? '');
  const [title, setTitle] = useState(edit?.title ?? '');
  const [detail, setDetail] = useState(edit?.detail ?? '');
  const [due, setDue] = useState(edit?.due_date ?? '');
  const [owner, setOwner] = useState('');
  const [error, setError] = useState('');

  const fixed = participant ?? followUpOf;
  const save = useMutation({
    mutationFn: () => {
      const body = {
        need,
        title,
        detail,
        due_date: due || null,
      };
      if (edit)
        return api<{ id: string }>(`/interventions/${edit.id}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      return post<{ id: string }>('/interventions', {
        ...body,
        ...(followUpOf
          ? { follow_up_of_id: followUpOf.id }
          : { participant_id: participant?.id ?? youthId }),
        ...(owner ? { owner_id: Number(owner) } : {}),
      });
    },
    onSuccess: (r) => {
      toast.success(edit ? 'Intervention updated.' : 'Intervention recorded.');
      refresh();
      onOpenChange(false);
      onSaved?.(r.id);
    },
    onError: (e) => setError(errorText(e)),
  });

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title={
        edit
          ? 'Edit intervention'
          : followUpOf
            ? 'Add a follow-up'
            : 'Record an intervention'
      }
      description="What support the youth needs and what will be done about it. Every change is kept in the history."
      submitLabel={edit ? 'Save changes' : 'Record'}
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!edit && !fixed && !youthId) return setError('Choose a youth.');
        if (!need) return setError('Choose the kind of support.');
        if (!title.trim()) return setError('Say what will be done.');
        setError('');
        save.mutate();
      }}
    >
      {!edit &&
        (fixed ? (
          <div className="space-y-1">
            <Label>Youth</Label>
            <p className="text-sm font-medium">
              {participant?.name ?? followUpOf?.participant}
            </p>
            {followUpOf && (
              <p className="text-xs text-muted-foreground">
                Following up: {followUpOf.title}
              </p>
            )}
          </div>
        ) : (
          <YouthPicker value={youthId} onChange={setYouthId} open={open} />
        ))}
      <div className="space-y-1.5">
        <Label>
          Kind of support
          <Required />
        </Label>
        <SelectField
          label="Choose kind of support"
          value={need}
          options={asOptions(options.data?.needs)}
          onChange={setNeed}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="case-title">
          What will be done
          <Required />
        </Label>
        <Input
          id="case-title"
          maxLength={200}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="case-detail">Details (optional)</Label>
        <Textarea
          id="case-detail"
          maxLength={4000}
          value={detail}
          onChange={(e) => setDetail(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="case-due">Due date (optional)</Label>
        <Input
          id="case-due"
          type="date"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
      </div>
      {!edit && canAssign && (
        <div className="space-y-1.5">
          <Label>Owner (defaults to you)</Label>
          <SelectField
            label="Choose owner"
            value={owner}
            emptyLabel="Me"
            options={(owners.data ?? []).map((u) => ({
              id: String(u.id),
              name: u.name,
            }))}
            onChange={setOwner}
          />
        </div>
      )}
    </FormModal>
  );
}

/** Move an intervention to its next status. Closing asks how it was verified; cancelling asks why. */
export function MoveDialog({
  open,
  onOpenChange,
  intervention,
  to,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  intervention: InterventionDetail;
  to: string;
}) {
  const refresh = useRefreshCases();
  const options = useCaseOptions(open);
  const [source, setSource] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const closing = to === 'closed';
  const cancelling = to === 'cancelled';
  const label = options.data?.statuses.find((s) => s.value === to)?.label ?? to;

  const move = useMutation({
    mutationFn: () =>
      post(`/interventions/${intervention.id}/move`, {
        to,
        note,
        ...(closing ? { verification_source: source } : {}),
      }),
    onSuccess: () => {
      toast.success(`Moved to ${label.toLowerCase()}.`);
      refresh();
      onOpenChange(false);
      setNote('');
      setSource('');
    },
    onError: (e) => setError(errorText(e)),
  });

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title={`Move to ${label.toLowerCase()}`}
      description={intervention.title}
      submitLabel="Move"
      pending={move.isPending}
      error={error}
      onSubmit={() => {
        if (closing && !source)
          return setError('Say how you know the support happened.');
        if (cancelling && !note.trim())
          return setError('Say why this is being cancelled.');
        setError('');
        move.mutate();
      }}
    >
      {closing && (
        <div className="space-y-1.5">
          <Label>
            How do you know the support happened?
            <Required />
          </Label>
          <SelectField
            label="Choose verification source"
            value={source}
            options={asOptions(options.data?.sources)}
            onChange={setSource}
          />
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="move-note">
          {cancelling ? 'Why is it being cancelled?' : 'Note (optional)'}
          {cancelling && <Required />}
        </Label>
        <Textarea
          id="move-note"
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

/** Hand a live intervention to another officer (caseload.reassign). */
export function AssignDialog({
  open,
  onOpenChange,
  intervention,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  intervention: InterventionDetail;
}) {
  const refresh = useRefreshCases();
  const owners = useOwners(open);
  const [owner, setOwner] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const assign = useMutation({
    mutationFn: () =>
      post(`/interventions/${intervention.id}/assign`, {
        owner_id: Number(owner),
        note,
      }),
    onSuccess: () => {
      toast.success('Intervention reassigned.');
      refresh();
      onOpenChange(false);
      setNote('');
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Reassign intervention"
      description={`Currently with ${intervention.owner || 'no one'}.`}
      submitLabel="Reassign"
      pending={assign.isPending}
      error={error}
      onSubmit={() => {
        if (!owner) return setError('Choose an officer.');
        setError('');
        assign.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label>
          New owner
          <Required />
        </Label>
        <SelectField
          label="Choose officer"
          value={owner}
          options={(owners.data ?? []).map((u) => ({
            id: String(u.id),
            name: u.name,
          }))}
          onChange={setOwner}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="assign-note">Note (optional)</Label>
        <Textarea
          id="assign-note"
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

/** Record a placement episode by hand, or correct one that was entered by hand. */
export function PlacementDialog({
  open,
  onOpenChange,
  participant,
  edit,
  prefill,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  participant?: { id: string; name: string };
  edit?: PlacementRow;
  /** Start the form from a selected referral: the employer and the role are already known. */
  prefill?: { employer?: { id: string; name: string }; designation?: string };
}) {
  const refresh = useRefreshCases();
  const options = usePlacementOptions(open);
  const [youthId, setYouthId] = useState('');
  const [pathway, setPathway] = useState(edit?.pathway ?? '');
  const [start, setStart] = useState(edit?.start_date ?? '');
  const [employerId, setEmployerId] = useState(
    edit?.employer_id ?? prefill?.employer?.id ?? '',
  );
  const [employerName, setEmployerName] = useState(
    edit && !edit.employer_id ? edit.employer : '',
  );
  const [designation, setDesignation] = useState(
    edit?.designation ?? prefill?.designation ?? '',
  );
  const [business, setBusiness] = useState(() => emptyBusiness(edit));
  const [work, setWork] = useState(() => emptyWork(edit));
  const [error, setError] = useState('');
  // D-081: the server refuses a second running placement and names the one already running.
  const [running, setRunning] = useState('');

  const save = useMutation({
    mutationFn: () => {
      const body = {
        pathway,
        start_date: start,
        employer_id: employerId || null,
        employer_name_source: employerId ? '' : employerName,
        designation,
        ...businessBody(pathway, business),
        ...workBody(pathway, work, options.data),
      };
      if (edit)
        return api(`/placements/${edit.id}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      return post('/placements', {
        ...body,
        participant_id: participant?.id ?? youthId,
      });
    },
    onSuccess: () => {
      toast.success(edit ? 'Placement corrected.' : 'Placement recorded.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        e.errors.some((x) => x.code === 'active_placement')
      )
        return setRunning(e.message);
      setError(errorText(e));
    },
  });

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title={edit ? 'Correct placement' : 'Record a placement'}
      description="One employment or training episode. A youth has one running placement at a time; ending one keeps it in the history."
      submitLabel={edit ? 'Save changes' : 'Record'}
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!edit && !participant && !youthId)
          return setError('Choose a youth.');
        if (!pathway) return setError('Choose the pathway.');
        if (!start) return setError('Enter the start date.');
        setError('');
        setRunning('');
        save.mutate();
      }}
    >
      {!edit &&
        (participant ? (
          <div className="space-y-1">
            <Label>Youth</Label>
            <p className="text-sm font-medium">{participant.name}</p>
          </div>
        ) : (
          <YouthPicker value={youthId} onChange={setYouthId} open={open} />
        ))}
      <div className="space-y-1.5">
        <Label>
          Pathway
          <Required />
        </Label>
        <SelectField
          label="Choose pathway"
          value={pathway}
          options={asOptions(options.data?.pathways)}
          onChange={setPathway}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="pl-start">
          Start date
          <Required />
        </Label>
        <Input
          id="pl-start"
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
      </div>
      <EmployerPicker
        value={employerId}
        onChange={setEmployerId}
        open={open}
        known={prefill?.employer}
      />
      {!employerId && (
        <div className="space-y-1.5">
          <Label htmlFor="pl-employer-name">
            Employer or business name (if not on the register)
          </Label>
          <Input
            id="pl-employer-name"
            maxLength={255}
            value={employerName}
            onChange={(e) => setEmployerName(e.target.value)}
          />
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="pl-designation">Role or designation</Label>
        <Input
          id="pl-designation"
          maxLength={255}
          value={designation}
          onChange={(e) => setDesignation(e.target.value)}
        />
      </div>
      {pathway && (
        <WorkFields
          id="pl-work"
          pathway={pathway}
          value={work}
          onChange={setWork}
          options={options.data}
        />
      )}
      {pathway === SELF_EMPLOYMENT && (
        <BusinessFields
          id="pl-business"
          value={business}
          onChange={setBusiness}
          options={options.data}
        />
      )}
      {running && (
        <div
          role="alert"
          className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm"
        >
          <p className="font-medium">{running}</p>
          <p>
            Close this form and find the running placement in the youth&apos;s
            placements. Use <strong>End</strong> if the job is over, or{' '}
            <strong>Changed employer</strong> if they moved straight to this
            one. A placement that has already ended can be recorded here with
            its end date.
          </p>
        </div>
      )}
    </FormModal>
  );
}

/** End a placement episode on a date, with the reason. */
export function EndPlacementDialog({
  open,
  onOpenChange,
  placement,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  placement: PlacementRow;
}) {
  const refresh = useRefreshCases();
  const [date, setDate] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const end = useMutation({
    mutationFn: () =>
      post(`/placements/${placement.id}/end`, {
        end_date: date,
        exit_reason: reason,
      }),
    onSuccess: () => {
      toast.success('Placement ended.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="End placement"
      description={`${placement.participant}: ${placement.pathway_label}${placement.employer ? ` at ${placement.employer}` : ''}. The episode stays in their history.`}
      submitLabel="End placement"
      pending={end.isPending}
      error={error}
      onSubmit={() => {
        if (!date) return setError('Enter the end date.');
        setError('');
        end.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="end-date">
          End date
          <Required />
        </Label>
        <Input
          id="end-date"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="end-reason">Why it ended (optional)</Label>
        <Input
          id="end-reason"
          maxLength={200}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

/** D-081: the youth left one job for another. Ends the running placement ("Changed employer")
 * and records the new one in one step; if either part is refused, nothing changes. */
export function ChangeEmployerDialog({
  open,
  onOpenChange,
  placement,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  placement: PlacementRow;
}) {
  const refresh = useRefreshCases();
  const options = usePlacementOptions(open);
  const [endDate, setEndDate] = useState('');
  const [start, setStart] = useState('');
  const [pathway, setPathway] = useState(placement.pathway ?? '');
  const [employerId, setEmployerId] = useState('');
  const [employerName, setEmployerName] = useState('');
  const [designation, setDesignation] = useState('');
  const [business, setBusiness] = useState(() => emptyBusiness());
  const [work, setWork] = useState(() => emptyWork());
  const [error, setError] = useState('');
  const change = useMutation({
    mutationFn: () =>
      post(`/placements/${placement.id}/change-employer`, {
        end_date: endDate,
        start_date: start,
        pathway,
        employer_id: employerId || null,
        employer_name_source: employerId ? '' : employerName,
        designation,
        ...businessBody(pathway, business),
        ...workBody(pathway, work, options.data),
      }),
    onSuccess: () => {
      toast.success('Old placement ended and new placement recorded.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Changed employer"
      description={`${placement.participant}: ends the placement${placement.employer ? ` at ${placement.employer}` : ''} with the reason "Changed employer" and starts the new one. Both stay in their history.`}
      submitLabel="End and record new"
      pending={change.isPending}
      error={error}
      onSubmit={() => {
        if (!endDate) return setError('Enter the date the old job ended.');
        if (!start) return setError('Enter the date the new job started.');
        if (start < endDate)
          return setError('The new job cannot start before the old one ended.');
        if (!pathway) return setError('Choose the pathway.');
        setError('');
        change.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="ce-end">
          Old job ended on
          <Required />
        </Label>
        <Input
          id="ce-end"
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="ce-start">
          New job started on
          <Required />
        </Label>
        <Input
          id="ce-start"
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label>
          Pathway
          <Required />
        </Label>
        <SelectField
          label="Choose pathway"
          value={pathway}
          options={asOptions(options.data?.pathways)}
          onChange={setPathway}
        />
      </div>
      <EmployerPicker value={employerId} onChange={setEmployerId} open={open} />
      {!employerId && (
        <div className="space-y-1.5">
          <Label htmlFor="ce-employer-name">
            New employer or business name (if not on the register)
          </Label>
          <Input
            id="ce-employer-name"
            maxLength={255}
            value={employerName}
            onChange={(e) => setEmployerName(e.target.value)}
          />
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="ce-designation">Role or designation</Label>
        <Input
          id="ce-designation"
          maxLength={255}
          value={designation}
          onChange={(e) => setDesignation(e.target.value)}
        />
      </div>
      {pathway && (
        <WorkFields
          id="ce-work"
          pathway={pathway}
          value={work}
          onChange={setWork}
          options={options.data}
        />
      )}
      {pathway === SELF_EMPLOYMENT && (
        <BusinessFields
          id="ce-business"
          value={business}
          onChange={setBusiness}
          options={options.data}
        />
      )}
    </FormModal>
  );
}

/** Record how staff confirmed the placement is real. */
export function VerifyPlacementDialog({
  open,
  onOpenChange,
  placement,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  placement: PlacementRow;
}) {
  const refresh = useRefreshCases();
  const options = usePlacementOptions(open);
  const [source, setSource] = useState('');
  const [error, setError] = useState('');
  const verify = useMutation({
    mutationFn: () => post(`/placements/${placement.id}/verify`, { source }),
    onSuccess: () => {
      toast.success('Placement verified.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Verify placement"
      description={`${placement.participant}: ${placement.pathway_label}. Say how you confirmed it.`}
      submitLabel="Verify"
      pending={verify.isPending}
      error={error}
      onSubmit={() => {
        if (!source) return setError('Choose how you confirmed it.');
        setError('');
        verify.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label>
          Verification source
          <Required />
        </Label>
        <SelectField
          label="Choose verification source"
          value={source}
          options={asOptions(options.data?.sources)}
          onChange={setSource}
        />
      </div>
    </FormModal>
  );
}
