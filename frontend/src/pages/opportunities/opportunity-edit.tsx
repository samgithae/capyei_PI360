import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';
import { ErrorState, LoadingState } from '@/components/states';
import { WhereWhatFields } from './opportunity-fields';

interface Detail {
  title: string;
  kind: string;
  sector_id: string | null;
  county_id: string | null;
  location: string;
  positions: number;
  description: string;
  closing_date: string | null;
}

const KINDS = ['job', 'internship', 'apprenticeship', 'other'].map((k) => ({
  id: k,
  name: k,
}));

/** Edit an opportunity's core fields (PATCH /opportunities/:id). Closed or expired ones are locked. */
export function EditOpportunity({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ['opportunity', id],
    queryFn: () => api<Detail>(`/opportunities/${id}`),
  });
  const [draft, setDraft] = useState<Partial<Detail>>({});
  const [error, setError] = useState('');
  const v = detail.data ? { ...detail.data, ...draft } : null;
  const patch = (p: Partial<Detail>) => setDraft((d) => ({ ...d, ...p }));

  const save = useMutation({
    mutationFn: (b: Detail) =>
      api(`/opportunities/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: b.title,
          kind: b.kind,
          sector_id: b.sector_id,
          county_id: b.county_id,
          location: b.location,
          positions: Number(b.positions),
          description: b.description,
          closing_date: b.closing_date || null,
        }),
      }),
    onSuccess: () => {
      toast.success('Opportunity updated.');
      void qc.invalidateQueries({ queryKey: ['opportunities'] });
      void qc.invalidateQueries({ queryKey: ['opportunity', id] });
      onClose();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && onClose()}
      title="Edit opportunity"
      description="Closed or expired opportunities cannot be edited; reopen them first."
      submitLabel="Save changes"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!v?.title.trim()) return setError('Enter a title.');
        setError('');
        save.mutate(v);
      }}
    >
      {detail.isPending && <LoadingState />}
      {detail.isError && (
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      )}
      {v && (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="oe-title">Title</Label>
            <Input
              id="oe-title"
              value={v.title}
              onChange={(e) => patch({ title: e.target.value })}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label>Type</Label>
              <SelectField
                label="Type"
                value={v.kind}
                options={KINDS}
                onChange={(x) => patch({ kind: x })}
                className="capitalize"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="oe-positions">Positions</Label>
              <Input
                id="oe-positions"
                type="number"
                min={1}
                value={v.positions}
                onChange={(e) => patch({ positions: Number(e.target.value) })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="oe-closing">Closing date</Label>
              <Input
                id="oe-closing"
                type="date"
                value={v.closing_date ?? ''}
                onChange={(e) => patch({ closing_date: e.target.value })}
              />
            </div>
          </div>
          <WhereWhatFields idPrefix="oe" value={v} onChange={patch} />
        </>
      )}
    </FormModal>
  );
}
