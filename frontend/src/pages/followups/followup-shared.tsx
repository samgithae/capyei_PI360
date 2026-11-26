import { useState } from 'react';
import {
  asOptions,
  businessBody,
  BusinessFields,
  emptyBusiness,
  emptyWork,
  errorText,
  Required,
  SELF_EMPLOYMENT,
  useOwners,
  usePlacementOptions,
  useRefreshCases,
  workBody,
  WorkFields,
  type Option,
} from '@/pages/cases/case-shared';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';

// Shapes returned by /api/v1/followups (backend: apps/casework/services.py, T-066).
export interface FollowUpRow {
  id: string;
  participant_id: string | null;
  participant: string;
  placement_id: string;
  employer: string;
  designation: string;
  placement_start: string | null;
  placement_ended: boolean;
  kind: 'early' | 'tracer';
  kind_label: string;
  label: string;
  due_date: string;
  status: 'open' | 'done' | 'unreachable' | 'cancelled';
  status_label: string;
  overdue: boolean;
  assigned_to_id: number | null;
  assigned_to: string;
  next_action: string;
  next_action_date: string | null;
  attempts: number | null;
}
export interface FollowUpAttempt {
  id: string;
  method: string;
  method_label: string;
  reached: boolean;
  made_on: string;
  note: string;
  made_by: string;
}
export interface FollowUpDetail extends FollowUpRow {
  response_note: string;
  still_employed: boolean | null;
  // NEW-034: what the youth is doing now. Blank on check-ins closed before it.
  outcome: FollowUpOutcome | '';
  outcome_label: string;
  leaving_reason_id: string | null;
  leaving_reason: string;
  left_on: string | null;
  observations: string;
  new_placement_id: string | null;
  evidence_source: string;
  evidence_source_label: string;
  closed_at: string | null;
  closed_by: string;
  attempt_list: FollowUpAttempt[];
  can: { work: boolean; assign: boolean };
}
export interface FollowUpPage {
  total: number;
  page_size: number;
  results: FollowUpRow[];
}
export interface FollowUpSummary {
  open: number;
  overdue: number;
  due_soon: number;
  done: number;
  unreachable: number;
  by_kind: Record<string, { label: string; open: number; done: number }>;
}
export type FollowUpOutcome =
  | 'same_employer'
  | 'changed_employer'
  | 'self_employed'
  | 'left_employment';
export interface LeavingReason {
  id: string;
  name: string;
  needs_note: boolean;
}
export interface FollowUpOptions {
  methods: Option[];
  sources: Option[];
  outcomes: Option[];
  leaving_reasons: LeavingReason[];
}
export interface ScheduleStep {
  id: string;
  kind: 'early' | 'tracer';
  kind_label: string;
  label: string;
  offset_days: number;
  active: boolean;
}

export const KIND_OPTIONS = [
  { id: 'early', name: 'Early follow-up' },
  { id: 'tracer', name: 'Tracer follow-up' },
];

/** Methods and evidence sources for the attempt and response forms. */
export function useFollowUpOptions(enabled = true) {
  return useQuery({
    queryKey: ['followup-options'],
    queryFn: () => api<FollowUpOptions>('/followups/options'),
    enabled,
    staleTime: 5 * 60_000,
  });
}

const today = () => new Date().toLocaleDateString('en-CA');

/** "Overdue" in red, or nothing: the badge only appears on open work past its date. */
export function OverdueBadge({ row }: { row: FollowUpRow }) {
  if (!row.overdue) return null;
  return (
    <Badge variant="destructive" appearance="light" className="ms-2">
      Overdue
    </Badge>
  );
}

/** Log one try at reaching the youth, with the next action if there is one. */
export function AttemptDialog({
  open,
  onOpenChange,
  followup,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  followup: FollowUpRow;
}) {
  const refresh = useRefreshCases();
  const options = useFollowUpOptions(open);
  const [method, setMethod] = useState('phone');
  const [reached, setReached] = useState('yes');
  const [madeOn, setMadeOn] = useState(today());
  const [note, setNote] = useState('');
  const [nextAction, setNextAction] = useState('');
  const [nextDate, setNextDate] = useState('');
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () =>
      post(`/followups/${followup.id}/attempts`, {
        method,
        reached: reached === 'yes',
        made_on: madeOn,
        note,
        next_action: nextAction,
        next_action_date: nextDate || null,
      }),
    onSuccess: () => {
      toast.success('Attempt recorded.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Log an attempt"
      description={`${followup.participant}: ${followup.label} check-in. Record each try, reached or not.`}
      submitLabel="Save attempt"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!madeOn) return setError('Enter the date of the attempt.');
        if (reached === 'no' && !note.trim())
          return setError('Say what happened when you could not reach them.');
        setError('');
        save.mutate();
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>
            How
            <Required />
          </Label>
          <SelectField
            label="Choose method"
            value={method}
            options={asOptions(options.data?.methods)}
            onChange={setMethod}
          />
        </div>
        <div className="space-y-1.5">
          <Label>
            Did you reach them?
            <Required />
          </Label>
          <SelectField
            label="Reached or not"
            value={reached}
            options={[
              { id: 'yes', name: 'Yes, reached' },
              { id: 'no', name: 'No, not reached' },
            ]}
            onChange={setReached}
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fu-made-on">
          Date
          <Required />
        </Label>
        <Input
          id="fu-made-on"
          type="date"
          max={today()}
          value={madeOn}
          onChange={(e) => setMadeOn(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fu-note">
          What happened{reached === 'no' ? '' : ' (optional)'}
          {reached === 'no' && <Required />}
        </Label>
        <Textarea
          id="fu-note"
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="fu-next">Next action (optional)</Label>
          <Input
            id="fu-next"
            maxLength={200}
            placeholder="e.g. Call again"
            value={nextAction}
            onChange={(e) => setNextAction(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fu-next-date">Next action date</Label>
          <Input
            id="fu-next-date"
            type="date"
            min={today()}
            value={nextDate}
            onChange={(e) => setNextDate(e.target.value)}
          />
        </div>
      </div>
    </FormModal>
  );
}

/** Record what the youth is doing now and how it was confirmed; this closes the check-in.
 * A change of work is recorded here too (NEW-034): leaving ends the placement, and a new job
 * or business starts one linked to it, so retention can tell same from other employer. */
export function CompleteDialog({
  open,
  onOpenChange,
  followup,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  followup: FollowUpRow;
}) {
  const refresh = useRefreshCases();
  const options = useFollowUpOptions(open);
  const placementOptions = usePlacementOptions(open);
  const [outcome, setOutcome] = useState('');
  const [source, setSource] = useState('');
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [leftOn, setLeftOn] = useState('');
  const [observations, setObservations] = useState('');
  // "Already on the Placements page": link the running placement instead of adding one.
  const [alreadyRecorded, setAlreadyRecorded] = useState(false);
  const [start, setStart] = useState('');
  const [employer, setEmployer] = useState('');
  const [designation, setDesignation] = useState('');
  const [work, setWork] = useState(() => emptyWork());
  const [business, setBusiness] = useState(() => emptyBusiness());
  const [error, setError] = useState('');

  const moved = outcome === 'changed_employer' || outcome === 'self_employed';
  const left = outcome === 'left_employment';
  const running = !followup.placement_ended;
  const pathway = outcome === 'self_employed' ? SELF_EMPLOYMENT : 'wage';
  const reasons = options.data?.leaving_reasons ?? [];
  const needsNote = reasons.find((r) => r.id === reason)?.needs_note ?? false;

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        outcome,
        evidence_source: source,
        note,
        observations,
      };
      if (left || moved) body.left_on = leftOn || null;
      if (left || moved) body.leaving_reason_id = reason || null;
      if (moved && !alreadyRecorded)
        body.new_job = {
          pathway,
          start_date: start,
          designation,
          ...(pathway === SELF_EMPLOYMENT
            ? {}
            : { employer_name_source: employer }),
          ...businessBody(pathway, business),
          ...workBody(pathway, work, placementOptions.data),
        };
      return post(`/followups/${followup.id}/complete`, body);
    },
    onSuccess: () => {
      toast.success('Check-in completed.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });

  const check = () => {
    if (!outcome) return 'Say what the youth is doing now.';
    if (!source) return 'Say how you confirmed it.';
    if (left && !reason) return 'Choose the reason for leaving.';
    if ((left || (moved && running)) && !leftOn)
      return 'Give the date they left the placement.';
    if (needsNote && !observations.trim() && !note.trim())
      return 'This reason needs a short explanation in the observations.';
    if (moved && !alreadyRecorded && !start)
      return 'Give the start date of the new work.';
    return '';
  };

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Record the response"
      description={`${followup.participant}: ${followup.label} check-in. This closes it.`}
      submitLabel="Complete check-in"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        const problem = check();
        if (problem) return setError(problem);
        setError('');
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label>
          What are they doing now?
          <Required />
        </Label>
        <SelectField
          label="Choose outcome"
          value={outcome}
          options={asOptions(options.data?.outcomes)}
          onChange={setOutcome}
        />
        {outcome === 'same_employer' && !running && (
          <p className="text-xs text-destructive">
            This placement has already ended, so they cannot still be in it.
          </p>
        )}
      </div>

      {(left || moved) && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>
                Reason for leaving
                {left && <Required />}
              </Label>
              <SelectField
                label="Choose reason"
                value={reason}
                options={reasons.map((r) => ({ id: r.id, name: r.name }))}
                onChange={setReason}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fu-left-on">
                Date they left
                {(left || running) && <Required />}
              </Label>
              <Input
                id="fu-left-on"
                type="date"
                value={leftOn}
                onChange={(e) => setLeftOn(e.target.value)}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {running
              ? `Saving ends the placement at ${followup.employer || 'the employer'} on this date.`
              : 'This check-in’s placement has already ended. If the youth has another placement still running, it ends on this date, so the date is needed then.'}
          </p>
        </>
      )}

      {moved && (
        <fieldset className="space-y-3 rounded-md border p-3">
          <legend className="px-1 text-sm font-medium">
            {outcome === 'self_employed' ? 'The business' : 'The new job'}
          </legend>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={alreadyRecorded}
              onChange={(e) => setAlreadyRecorded(e.target.checked)}
            />
            Already added on the Placements page: link it instead
          </label>
          <p className="text-xs text-muted-foreground">
            {alreadyRecorded
              ? 'The work already on the Placements page is linked to this check-in. Nothing new is created.'
              : `Saving creates a new placement for this ${outcome === 'self_employed' ? 'business' : 'job'}, linked to the earlier one. The earlier placement is kept in the history, not overwritten.`}
          </p>
          {!alreadyRecorded && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="fu-start">
                    Start date
                    <Required />
                  </Label>
                  <Input
                    id="fu-start"
                    type="date"
                    value={start}
                    onChange={(e) => setStart(e.target.value)}
                  />
                </div>
                {outcome === 'changed_employer' && (
                  <div className="space-y-1.5">
                    <Label htmlFor="fu-employer">Employer name</Label>
                    <Input
                      id="fu-employer"
                      maxLength={255}
                      value={employer}
                      onChange={(e) => setEmployer(e.target.value)}
                    />
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="fu-designation">
                  {outcome === 'self_employed' ? 'Role' : 'Job title'}
                </Label>
                <Input
                  id="fu-designation"
                  maxLength={255}
                  value={designation}
                  onChange={(e) => setDesignation(e.target.value)}
                />
              </div>
              <WorkFields
                id="fu-work"
                pathway={pathway}
                value={work}
                onChange={setWork}
                options={placementOptions.data}
              />
              {outcome === 'self_employed' && (
                <BusinessFields
                  id="fu-business"
                  value={business}
                  onChange={setBusiness}
                  options={placementOptions.data}
                />
              )}
            </>
          )}
        </fieldset>
      )}

      <div className="space-y-1.5">
        <Label>
          How did you confirm it?
          <Required />
        </Label>
        <SelectField
          label="Choose evidence"
          value={source}
          options={asOptions(options.data?.sources)}
          onChange={setSource}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fu-observations">
          Observations{needsNote ? '' : ' (optional)'}
          {needsNote && <Required />}
        </Label>
        <Textarea
          id="fu-observations"
          maxLength={2000}
          placeholder="What you learned about how they are doing."
          value={observations}
          onChange={(e) => setObservations(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fu-response">Note (optional)</Label>
        <Textarea
          id="fu-response"
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

/** Close the check-in because the youth could not be reached after trying. */
export function UnreachableDialog({
  open,
  onOpenChange,
  followup,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  followup: FollowUpRow;
}) {
  const refresh = useRefreshCases();
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () => post(`/followups/${followup.id}/unreachable`, { note }),
    onSuccess: () => {
      toast.success('Marked as unreachable.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Mark as unreachable"
      description={`${followup.participant}: ${followup.label} check-in. Needs at least one logged attempt.`}
      submitLabel="Mark unreachable"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        setError('');
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="fu-unreachable">Note (optional)</Label>
        <Textarea
          id="fu-unreachable"
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

/** Cancel a check-in that no longer applies. It is kept in the history with the reason. */
export function CancelDialog({
  open,
  onOpenChange,
  followup,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  followup: FollowUpRow;
}) {
  const refresh = useRefreshCases();
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () => post(`/followups/${followup.id}/cancel`, { reason }),
    onSuccess: () => {
      toast.success('Check-in cancelled.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Cancel this check-in"
      description={`${followup.participant}: ${followup.label}. It stays in the history.`}
      submitLabel="Cancel check-in"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!reason.trim()) return setError('Say why it is being cancelled.');
        setError('');
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="fu-cancel">
          Why
          <Required />
        </Label>
        <Textarea
          id="fu-cancel"
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

/** Hand a check-in to another officer (caseload.reassign). */
export function AssignFollowUpDialog({
  open,
  onOpenChange,
  followup,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  followup: FollowUpRow;
}) {
  const refresh = useRefreshCases();
  const owners = useOwners(open);
  const [owner, setOwner] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () =>
      post(`/followups/${followup.id}/assign`, {
        owner_id: Number(owner),
        note,
      }),
    onSuccess: () => {
      toast.success('Check-in reassigned.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Reassign check-in"
      description={`Currently with ${followup.assigned_to || 'no one'}.`}
      submitLabel="Reassign"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!owner) return setError('Choose an officer.');
        setError('');
        save.mutate();
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
        <Label htmlFor="fu-assign-note">Note (optional)</Label>
        <Textarea
          id="fu-assign-note"
          maxLength={500}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
    </FormModal>
  );
}
