import { useState } from 'react';
import {
  asOptions,
  errorText,
  Required,
  useOwners,
  useRefreshCases,
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
export interface FollowUpOptions {
  methods: Option[];
  sources: Option[];
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

/** Record the youth's answer and how it was confirmed; this closes the check-in. */
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
  const [employed, setEmployed] = useState('');
  const [source, setSource] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () =>
      post(`/followups/${followup.id}/complete`, {
        still_employed: employed === 'yes',
        evidence_source: source,
        note,
      }),
    onSuccess: () => {
      toast.success('Check-in completed.');
      refresh();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
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
        if (!employed)
          return setError('Say whether they are still in the placement.');
        if (!source) return setError('Say how you confirmed it.');
        setError('');
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label>
          Still in the placement?
          <Required />
        </Label>
        <SelectField
          label="Choose answer"
          value={employed}
          options={[
            { id: 'yes', name: 'Yes, still in the placement' },
            { id: 'no', name: 'No, no longer' },
          ]}
          onChange={setEmployed}
        />
        {employed === 'no' && (
          <p className="text-xs text-muted-foreground">
            This only records the answer. To end the placement, or record a move
            to a new employer, use the Placements page.
          </p>
        )}
      </div>
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
