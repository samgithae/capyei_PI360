import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';
import { ErrorState, LoadingState } from '@/components/states';

interface Detail {
  given_name: string;
  family_name: string;
  other_names: string;
  gender: string;
  status: string;
}

const GENDERS = ['female', 'male', 'other', 'unknown'];
const STATUSES = ['active', 'completed', 'withdrawn', 'unknown'];
const opts = (xs: string[]) => xs.map((x) => ({ id: x, name: x }));

/** Edit a participant's name, gender and status (what the API allows; PATCH /participants/:id). */
export function EditParticipant({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ['participant', id],
    queryFn: () => api<Detail>(`/participants/${id}`),
  });
  const [v, setV] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (detail.data && !v) setV(detail.data);
  }, [detail.data, v]);

  const save = useMutation({
    // Send only what changed, so untouched blank names on imported records stay as they are.
    mutationFn: (body: Detail) => {
      const changed = Object.fromEntries(
        (Object.keys(body) as (keyof Detail)[])
          .filter((k) => body[k] !== detail.data?.[k])
          .map((k) => [k, body[k]]),
      );
      if (Object.keys(changed).length === 0) return Promise.resolve(null);
      return api(`/participants/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(changed),
      });
    },
    onSuccess: () => {
      toast.success('Participant updated.');
      void qc.invalidateQueries({ queryKey: ['participants'] });
      void qc.invalidateQueries({ queryKey: ['participant', id] });
      onClose();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  const text = (
    key: 'given_name' | 'family_name' | 'other_names',
    label: string,
  ) =>
    v && (
      <div className="space-y-1.5">
        <Label htmlFor={`pe-${key}`}>{label}</Label>
        <Input
          id={`pe-${key}`}
          value={v[key]}
          onChange={(e) => setV({ ...v, [key]: e.target.value })}
        />
      </div>
    );

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && onClose()}
      title="Edit participant"
      description="Names, gender and status. Programme and cohort come from imports."
      submitLabel="Save changes"
      pending={save.isPending}
      error={error}
      onSubmit={() => v && save.mutate(v)}
    >
      {detail.isPending && <LoadingState />}
      {detail.isError && (
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      )}
      {v && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            {text('given_name', 'Given name')}
            {text('family_name', 'Family name')}
          </div>
          {text('other_names', 'Other names')}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Gender</Label>
              <SelectField
                label="Gender"
                value={v.gender}
                options={opts(GENDERS)}
                onChange={(x) => setV({ ...v, gender: x })}
                className="capitalize"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <SelectField
                label="Status"
                value={v.status}
                options={opts(STATUSES)}
                onChange={(x) => setV({ ...v, status: x })}
                className="capitalize"
              />
            </div>
          </div>
        </>
      )}
    </FormModal>
  );
}
