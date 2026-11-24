import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { errorText } from '@/pages/cases/case-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SelectField } from '@/components/shared/select-field';

interface Doc {
  disability: 'not_recorded' | 'yes' | 'no';
  description: string;
  recorded_at: string | null;
}

const OPTIONS = [
  { id: 'not_recorded', name: 'Not recorded' },
  { id: 'yes', name: 'Yes' },
  { id: 'no', name: 'No' },
];

/**
 * Whether the youth has a disability (D-082). Yes or No, with a short description when Yes; there
 * is no "prefer not to say", and a youth nobody has asked stays "Not recorded". It shows only to
 * people holding `participants.view_disability`, and only while the server switch is on (the
 * route answers 404 otherwise, which hides the card). Every view and change is logged.
 */
export function DisabilityCard({ participantId }: { participantId: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const allowed = can('participants.view_disability');
  const key = ['participant-disability', participantId];
  const doc = useQuery({
    queryKey: key,
    queryFn: () => api<Doc>(`/participants/${participantId}/disability`),
    enabled: allowed,
    retry: false,
    // Each read is logged, so do not re-read on every window focus.
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });
  const [answer, setAnswer] = useState<Doc['disability']>('not_recorded');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (doc.data) {
      setAnswer(doc.data.disability);
      setDescription(doc.data.description);
    }
  }, [doc.data]);

  const save = useMutation({
    mutationFn: () =>
      api<Doc>(`/participants/${participantId}/disability`, {
        method: 'PUT',
        body: JSON.stringify({ disability: answer, description }),
      }),
    onSuccess: (d) => {
      qc.setQueryData(key, d);
      setError('');
      toast.success('Disability answer saved.');
    },
    onError: (e) => setError(errorText(e)),
  });

  if (!allowed) return null;
  if (doc.error instanceof ApiError && doc.error.status === 404) return null;
  if (doc.isLoading || !doc.data) return null;
  const dirty =
    answer !== doc.data.disability ||
    (answer === 'yes' ? description : '') !== doc.data.description;
  return (
    <Card role="group" aria-label="Disability">
      <CardHeader>
        <CardTitle>Disability</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Asked so the project can plan reasonable adjustments and report
          inclusion. Answering is the youth&apos;s choice; leave it as Not
          recorded if they would rather not say. Everyone who opens or changes
          this is logged.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Does the youth have a disability?</Label>
            <SelectField
              label="Disability"
              value={answer}
              options={OPTIONS}
              onChange={(x) => setAnswer(x as Doc['disability'])}
            />
          </div>
          {answer === 'yes' && (
            <div className="space-y-1.5">
              <Label htmlFor="disability-description">
                Description (optional)
              </Label>
              <Input
                id="disability-description"
                maxLength={300}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          )}
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate()}
        >
          Save answer
        </Button>
      </CardContent>
    </Card>
  );
}
