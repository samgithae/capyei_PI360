import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { errorText } from '@/pages/cases/case-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { Detail } from './types';

interface Event {
  kind: 'flagged' | 'reviewed';
  reason_label: string;
  note: string;
  by: string;
  at: string;
}

/**
 * The review flag on one youth (D-084): why it is on the work list, a way to mark it reviewed or
 * flag it, and the history. It blocks nothing.
 */
export function ReviewStrip({ p }: { p: Detail }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const canEdit = can('participants.edit') && !p.archived;
  const state = p.review?.state ?? 'none';
  const [mode, setMode] = useState<'' | 'flag' | 'done'>('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [showHistory, setShowHistory] = useState(false);

  const history = useQuery({
    queryKey: ['participant-review', p.id],
    queryFn: () => api<{ results: Event[] }>(`/participants/${p.id}/review`),
    enabled: showHistory,
  });
  const run = useMutation({
    mutationFn: () =>
      mode === 'flag'
        ? post(`/participants/${p.id}/review`, { note })
        : api(`/participants/${p.id}/review`, {
            method: 'DELETE',
            body: JSON.stringify({ note }),
          }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['participant'] });
      void qc.invalidateQueries({ queryKey: ['participants'] });
      void qc.invalidateQueries({ queryKey: ['participant-review', p.id] });
      setMode('');
      setNote('');
      setError('');
    },
    onError: (e) => setError(errorText(e)),
  });

  if (state === 'none' && !canEdit) return null;
  return (
    <div className="mt-4 space-y-2 border-t border-border pt-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {state === 'needs_review' ? (
          <>
            <Badge variant="warning" appearance="light" size="sm">
              Needs review
            </Badge>
            <span className="text-muted-foreground">
              {p.review?.reason_label}
            </span>
          </>
        ) : (
          <span className="text-muted-foreground">
            {state === 'reviewed' ? 'Reviewed' : 'No review needed'}
          </span>
        )}
        {canEdit && state === 'needs_review' && (
          <Button size="sm" variant="outline" onClick={() => setMode('done')}>
            Mark reviewed
          </Button>
        )}
        {canEdit && state !== 'needs_review' && (
          <Button size="sm" variant="outline" onClick={() => setMode('flag')}>
            Flag for review
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setShowHistory((v) => !v)}
        >
          {showHistory ? 'Hide review history' : 'Review history'}
        </Button>
      </div>
      {mode && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (mode === 'flag' && !note.trim()) {
              setError('Say why this record needs a look.');
              return;
            }
            run.mutate();
          }}
        >
          <label className="sr-only" htmlFor="review-note">
            {mode === 'flag'
              ? 'Why it needs a look'
              : 'Reviewed note (optional)'}
          </label>
          <Input
            id="review-note"
            className="max-w-md"
            maxLength={500}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={
              mode === 'flag'
                ? 'Why does it need a look? (required)'
                : 'Note (optional). Do not add contact details.'
            }
          />
          <Button size="sm" type="submit" disabled={run.isPending}>
            {mode === 'flag' ? 'Flag it' : 'Confirm reviewed'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            type="button"
            onClick={() => setMode('')}
          >
            Cancel
          </Button>
          {error && (
            <span role="alert" className="text-destructive">
              {error}
            </span>
          )}
        </form>
      )}
      {showHistory && (
        <ul className="space-y-1 text-muted-foreground">
          {history.data?.results.length === 0 && <li>No review events yet.</li>}
          {history.data?.results.map((e, i) => (
            <li key={i}>
              {e.kind === 'flagged' ? 'Flagged' : 'Marked reviewed'}
              {e.reason_label && ` (${e.reason_label})`}
              {e.by && ` by ${e.by}`} on {e.at.slice(0, 10)}
              {e.note && `: ${e.note}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
