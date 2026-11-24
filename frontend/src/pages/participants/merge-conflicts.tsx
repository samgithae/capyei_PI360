// NEW-077: what a merge would do, and the conflicts that hold it. The server decides what is a
// conflict; this screen only shows it and records the officer's explicit choice.
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ApiError, post } from '@/lib/api';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export type Keep = 'survivor' | 'merged';

export interface ReviewField {
  field: string;
  label: string;
  survivor: string | number | null;
  merged: string | number | null;
  conflict: boolean;
  keep: Keep | null;
}

export interface ConflictItem {
  id: string;
  side: 'survivor' | 'merged';
  employer?: string;
  pathway?: string;
  start_date?: string | null;
  designation?: string;
}

export interface Critical {
  code: string;
  message: string;
  items: ConflictItem[];
  actions: string[];
  hint: string;
  looks_same?: boolean;
}

export interface Review {
  survivor: string;
  merged: string;
  fields: ReviewField[];
  critical: Critical[];
}

export interface Resolution {
  id: string;
  conflict: string;
  action: string;
  reason: string;
  decided_by: string;
  decided_at: string;
}

/** Labels of real conflicts the steward has not chosen yet. */
export function unchosen(
  fields: ReviewField[],
  choices: Record<string, Keep>,
): string[] {
  return fields
    .filter((f) => f.conflict && !choices[f.field])
    .map((f) => f.label);
}

const SIDE = { survivor: 'kept record', merged: 'merged record' } as const;
const ACTION = {
  end: 'ended a placement',
  same: 'marked a placement as recorded twice',
} as const;

function describe(i: ConflictItem) {
  return [
    i.employer || 'Employer not named',
    i.designation,
    i.start_date ? `from ${i.start_date}` : 'start date not recorded',
  ]
    .filter(Boolean)
    .join(', ');
}

export function CriticalList({ conflicts }: { conflicts: Critical[] }) {
  if (conflicts.length === 0) return null;
  return (
    <Alert variant="destructive" appearance="light">
      <AlertTitle>
        This merge will wait for {conflicts.length} conflict
        {conflicts.length > 1 ? 's' : ''} to be resolved
      </AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-5">
          {conflicts.map((c) => (
            <li key={c.code}>
              {c.message} {c.hint}
              {c.items.some((i) => i.employer !== undefined) && (
                <ul className="pl-4">
                  {c.items.map((i) => (
                    <li key={i.id}>
                      {SIDE[i.side]}: {describe(i)}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

export function ResolutionList({ rows }: { rows: Resolution[] }) {
  if (rows.length === 0) return null;
  return (
    <ul className="space-y-1 text-sm">
      {rows.map((r) => (
        <li key={r.id}>
          {r.decided_by} {ACTION[r.action as keyof typeof ACTION] ?? r.action}{' '}
          on {r.decided_at.slice(0, 10)}. Reason: {r.reason}
        </li>
      ))}
    </ul>
  );
}

/** Resolve two running placements: end one that is over, or mark one as the same placement
 * recorded twice (it is kept and points at the other). Nothing is deleted. */
export function PlacementResolver({
  candidateId,
  conflict,
  canEditPlacements,
  onDone,
}: {
  candidateId: string;
  conflict: Critical;
  canEditPlacements: boolean;
  onDone: () => void;
}) {
  const [placement, setPlacement] = useState('');
  const [action, setAction] = useState<'end' | 'same' | ''>('');
  const [endDate, setEndDate] = useState('');
  const [reason, setReason] = useState('');
  const chosen = conflict.items.find((i) => i.id === placement);
  const keep = conflict.items.find((i) => chosen && i.side !== chosen.side);
  const resolve = useMutation({
    mutationFn: () =>
      post(`/participants/duplicates/${candidateId}/resolve`, {
        action,
        placement_id: placement,
        keep_id: action === 'same' ? keep?.id : undefined,
        end_date: action === 'end' ? endDate : undefined,
        reason,
      }),
    onSuccess: onDone,
  });
  if (!canEditPlacements) {
    return (
      <p className="text-sm text-muted-foreground">
        Resolving placements needs the right to edit placements.
      </p>
    );
  }
  const ready =
    placement &&
    action &&
    reason.trim() &&
    (action === 'same' ? keep : endDate) &&
    !resolve.isPending;
  return (
    <fieldset className="space-y-2 rounded-lg border p-3 text-sm">
      <legend className="px-1 font-medium">Resolve the two placements</legend>
      {conflict.looks_same && (
        <p className="text-muted-foreground">
          These look like the same placement (same employer and start date).
          Check before you choose.
        </p>
      )}
      {conflict.items.map((i) => (
        <label key={i.id} className="flex items-center gap-2">
          <input
            type="radio"
            name={`placement-${candidateId}`}
            checked={placement === i.id}
            onChange={() => setPlacement(i.id)}
          />
          {SIDE[i.side]}: {describe(i)}
        </label>
      ))}
      <div className="flex flex-wrap gap-3">
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name={`action-${candidateId}`}
            checked={action === 'same'}
            onChange={() => setAction('same')}
          />
          Same placement, recorded twice
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name={`action-${candidateId}`}
            checked={action === 'end'}
            onChange={() => setAction('end')}
          />
          Different placements: this one has ended
        </label>
      </div>
      {action === 'same' && chosen && keep && (
        <p className="text-muted-foreground">
          The selected row is kept but marked as recorded twice; the{' '}
          {SIDE[keep.side]}'s placement ({describe(keep)}) stays running.
        </p>
      )}
      {action === 'end' && (
        <Input
          type="date"
          aria-label="End date"
          className="max-w-48"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
        />
      )}
      <div className="flex flex-wrap gap-2">
        <Input
          aria-label="Resolution reason"
          placeholder="Why (kept with the merge)"
          className="max-w-md"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <Button disabled={!ready} onClick={() => resolve.mutate()}>
          Record resolution
        </Button>
      </div>
      {resolve.error && (
        <p role="alert" className="text-destructive">
          {resolve.error instanceof ApiError
            ? resolve.error.message
            : 'Something went wrong.'}
        </p>
      )}
    </fieldset>
  );
}
