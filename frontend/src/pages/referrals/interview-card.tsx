import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Section } from '@/components/shared/info-card';

interface Props {
  id: string;
  at: string | null;
  place: string;
  note: string;
  onSaved: () => void;
}

/** datetime-local wants "YYYY-MM-DDTHH:mm" in local time. */
const toLocal = (iso: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/** Interview time, place and a note the learner will see. Shown while the referral is at interview. */
export function InterviewCard({ id, at, place, note, onSaved }: Props) {
  const [when, setWhen] = useState(toLocal(at));
  const [where, setWhere] = useState(place);
  const [text, setText] = useState(note);
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () =>
      api(`/referrals/${id}/interview`, {
        method: 'PUT',
        body: JSON.stringify({
          at: new Date(when).toISOString(),
          place: where,
          note: text,
        }),
      }),
    onSuccess: () => {
      toast.success('Interview details saved. The learner can now see them.');
      setError('');
      onSaved();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Something went wrong.'),
  });

  return (
    <Section title="Interview details">
      <div className="space-y-3 p-5">
        <p className="text-sm text-muted-foreground">
          The learner sees these on their page. Write the note for them: what to
          bring, who to ask for.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="iv-at">Date and time</Label>
            <Input
              id="iv-at"
              type="datetime-local"
              value={when}
              onChange={(e) => setWhen(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="iv-place">Place</Label>
            <Input
              id="iv-place"
              value={where}
              maxLength={200}
              onChange={(e) => setWhere(e.target.value)}
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="iv-note">Note for the learner</Label>
          <Input
            id="iv-note"
            value={text}
            maxLength={500}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button
          disabled={!when || save.isPending}
          onClick={() => save.mutate()}
        >
          Save interview details
        </Button>
      </div>
    </Section>
  );
}
