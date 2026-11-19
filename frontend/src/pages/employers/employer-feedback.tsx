import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { errorText } from '@/pages/cases/case-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Section } from '@/components/shared/info-card';
import { FormModal } from '@/components/shared/modals';
import { ErrorState, LoadingState } from '@/components/states';

export interface Feedback {
  id: string;
  party: string;
  party_label: string;
  source: string;
  source_label: string;
  rating: number;
  note: string;
  given_on: string;
  recorded_by: string;
}

const PARTIES = [
  ['employer', 'The employer'],
  ['youth', 'A young person placed there'],
] as const;
const SOURCES = [
  ['call', 'Phone call'],
  ['visit', 'Visit'],
  ['email', 'E-mail'],
  ['meeting', 'Meeting'],
] as const;

const today = () => new Date().toLocaleDateString('en-CA');

const selectClass =
  'block h-9 w-full rounded-md border border-input bg-background px-3 text-sm';

/** Feedback officers have logged about this employer (D-013). Each entry names its source; only
 * entries with a source feed the "Employer feedback" indicator. */
export function EmployerFeedback({ id }: { id: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const key = ['employer-feedback', id];
  const list = useQuery({
    queryKey: key,
    queryFn: () => api<{ results: Feedback[] }>(`/employers/${id}/feedback`),
    enabled: can('employers.view'),
  });
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Feedback | null>(null);
  const [party, setParty] = useState('employer');
  const [source, setSource] = useState('call');
  const [rating, setRating] = useState('4');
  const [givenOn, setGivenOn] = useState(today());
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');

  const changed = () => {
    void qc.invalidateQueries({ queryKey: key });
    void qc.invalidateQueries({ queryKey: ['employer-evidence', id] });
  };
  const add = useMutation({
    mutationFn: () =>
      post(`/employers/${id}/feedback`, {
        party,
        source,
        rating: Number(rating),
        given_on: givenOn,
        note: note.trim(),
      }),
    onSuccess: () => {
      toast.success('Feedback recorded');
      setAdding(false);
      setNote('');
      changed();
    },
    onError: (e) => setError(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: (f: Feedback) =>
      api<void>(`/employers/${id}/feedback/${f.id}`, {
        method: 'DELETE',
        body: JSON.stringify({ reason: reason.trim() }),
      }),
    onSuccess: () => {
      toast.success('Feedback removed');
      setRemoving(null);
      setReason('');
      changed();
    },
    onError: (e) => setError(errorText(e)),
  });

  if (!can('employers.view')) return null;
  return (
    <Section
      title="Feedback"
      description="What the employer, or a young person placed there, told an officer. Each entry needs a source."
    >
      <div className="space-y-3 text-sm">
        {can('employers.edit') && (
          <Button
            variant="outline"
            onClick={() => {
              setError('');
              setAdding(true);
            }}
          >
            Add feedback
          </Button>
        )}
        {list.isError ? (
          <ErrorState error={list.error} onRetry={() => void list.refetch()} />
        ) : !list.data ? (
          <LoadingState rows={2} />
        ) : list.data.results.length === 0 ? (
          <p className="text-muted-foreground">No feedback recorded yet.</p>
        ) : (
          <ul className="divide-y">
            {list.data.results.map((f) => (
              <li key={f.id} className="space-y-1 py-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">
                    {f.rating} out of 5 · {f.party_label}
                  </span>
                  <span className="text-muted-foreground">
                    {f.given_on} · {f.source_label}
                    {f.recorded_by && ` · ${f.recorded_by}`}
                  </span>
                </div>
                {f.note && <p>{f.note}</p>}
                {can('employers.edit') && (
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setError('');
                      setRemoving(f);
                    }}
                  >
                    Remove
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <FormModal
        open={adding}
        onOpenChange={setAdding}
        title="Add feedback"
        description="Record what you were told. The source is required; entries without one are not counted."
        submitLabel="Save"
        pending={add.isPending}
        error={error}
        onSubmit={() => {
          setError('');
          add.mutate();
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="fb-party">Who gave it</Label>
          <select
            id="fb-party"
            className={selectClass}
            value={party}
            onChange={(e) => setParty(e.target.value)}
          >
            {PARTIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fb-source">Source</Label>
          <select
            id="fb-source"
            className={selectClass}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            {SOURCES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fb-rating">Rating (1 poor to 5 very good)</Label>
          <select
            id="fb-rating"
            className={selectClass}
            value={rating}
            onChange={(e) => setRating(e.target.value)}
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fb-date">Date it was given</Label>
          <Input
            id="fb-date"
            type="date"
            max={today()}
            value={givenOn}
            onChange={(e) => setGivenOn(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fb-note">Short note (optional)</Label>
          <Input
            id="fb-note"
            maxLength={1000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
      </FormModal>

      <FormModal
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Remove feedback"
        description="Use this for an entry made by mistake. The reason is kept in the audit log."
        submitLabel="Remove"
        pending={remove.isPending}
        error={error}
        onSubmit={() => {
          if (!reason.trim()) {
            setError('Say why this is being removed.');
            return;
          }
          setError('');
          if (removing) remove.mutate(removing);
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="fb-reason">Reason</Label>
          <Input
            id="fb-reason"
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
      </FormModal>
    </Section>
  );
}
