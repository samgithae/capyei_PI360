import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Notice } from '@/components/states';

interface Review {
  clusters: {
    key: string;
    count: number;
    spellings: { text: string; count: number }[];
    suggested: { id: string; name: string }[];
  }[];
  unmapped_statuses: { value: string; count: number }[];
  held: number;
}

// What a status value can mean (D-061). "placed" outcomes count as placements (D-011).
const MEANINGS: Record<
  string,
  { status: string; pathway: string; is_placement: boolean }
> = {
  wage: { status: 'placed', pathway: 'wage', is_placement: true },
  self_employment: {
    status: 'placed',
    pathway: 'self_employment',
    is_placement: true,
  },
  further_training: {
    status: 'placed',
    pathway: 'further_training',
    is_placement: true,
  },
  work_based_learning: {
    status: 'placed',
    pathway: 'work_based_learning',
    is_placement: true,
  },
  declined: { status: 'declined', pathway: '', is_placement: false },
};
const MEANING_LABEL: Record<string, string> = {
  wage: 'Wage employment (placed)',
  self_employment: 'Self-employment (placed)',
  further_training: 'Further training (placed)',
  work_based_learning: 'Work-based learning (placed)',
  declined: 'Not a placement (offer declined)',
};

/** Review step for a placement import: decide which statuses mean what and which organisation
 * spellings are the same employer. Nothing here is final until the batch is approved. */
export function PlacementReview({
  id,
  canDecide,
}: {
  id: string;
  canDecide: boolean;
}) {
  const qc = useQueryClient();
  const review = useQuery({
    queryKey: ['import-review', id],
    queryFn: () => api<Review>(`/imports/batches/${id}/review`),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['import-review', id] });
    qc.invalidateQueries({ queryKey: ['import-batch', id] });
    qc.invalidateQueries({ queryKey: ['import-rows', id] });
  };
  const mapStatus = useMutation({
    mutationFn: (v: { source_value: string; meaning: string }) =>
      post<Review>(`/imports/batches/${id}/review/statuses`, {
        source_value: v.source_value,
        ...MEANINGS[v.meaning],
      }),
    onSuccess: () => {
      refresh();
      toast.success('Status mapped. Re-check the batch to release its rows.');
    },
  });
  const decide = useMutation({
    mutationFn: (v: {
      key: string;
      spellings: string[];
      action: 'link' | 'create' | 'apart';
      employer_id?: string;
    }) => post<Review>(`/imports/batches/${id}/review/employers`, v),
    onSuccess: () => {
      refresh();
      toast.success('Decision saved.');
    },
  });
  const recheck = useMutation({
    mutationFn: () => post(`/imports/batches/${id}/recheck`),
    onSuccess: () => {
      refresh();
      toast.success('Held rows re-checked.');
    },
  });

  const error = mapStatus.error ?? decide.error ?? recheck.error;
  const r = review.data;
  if (!r) return null;

  return (
    <div className="space-y-4">
      {error && (
        <Notice tone="error" title="This could not be done">
          {error instanceof ApiError ? error.message : 'Something went wrong.'}
        </Notice>
      )}

      <Card>
        <CardContent className="space-y-3">
          <h2 className="font-medium">Statuses with no meaning yet</h2>
          {r.unmapped_statuses.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Every status in this file is mapped.
            </p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Rows with these values are held until someone says what they
                mean. The choice applies to every later file too.
              </p>
              {r.unmapped_statuses.map((u) => (
                <div
                  key={u.value}
                  className="flex flex-wrap items-center gap-2"
                >
                  <span className="min-w-48 text-sm">
                    {u.value} ({u.count} rows)
                  </span>
                  <Select
                    disabled={!canDecide || mapStatus.isPending}
                    onValueChange={(meaning) =>
                      mapStatus.mutate({ source_value: u.value, meaning })
                    }
                  >
                    <SelectTrigger
                      aria-label={`Meaning of ${u.value}`}
                      className="w-72"
                    >
                      <SelectValue placeholder="Choose what it means" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(MEANING_LABEL).map(([k, label]) => (
                        <SelectItem key={k} value={k}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </>
          )}
          {r.held > 0 && (
            <Button
              variant="outline"
              disabled={!canDecide || recheck.isPending}
              onClick={() => recheck.mutate()}
            >
              Re-check {r.held} held rows
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3">
          <h2 className="font-medium">Organisation names</h2>
          <p className="text-sm text-muted-foreground">
            Spellings are grouped as suggestions only. You decide: link a group
            to an employer already on file, create one new employer, or keep the
            spellings apart. You can also load without deciding; the name is
            kept as written and linked later.
          </p>
          {r.clusters.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Nothing left to decide.
            </p>
          )}
          {r.clusters.slice(0, 50).map((c) => {
            const spellings = c.spellings.map((s) => s.text);
            return (
              <div key={c.key} className="rounded-md border p-3 text-sm">
                <div className="font-medium">
                  {c.spellings.map((s) => `${s.text} (${s.count})`).join(' / ')}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {c.suggested.map((e) => (
                    <Button
                      key={e.id}
                      size="sm"
                      variant="outline"
                      disabled={!canDecide || decide.isPending}
                      onClick={() =>
                        decide.mutate({
                          key: c.key,
                          spellings,
                          action: 'link',
                          employer_id: e.id,
                        })
                      }
                    >
                      Link to {e.name}
                    </Button>
                  ))}
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!canDecide || decide.isPending}
                    onClick={() =>
                      decide.mutate({ key: c.key, spellings, action: 'create' })
                    }
                  >
                    Create one new employer
                  </Button>
                  {spellings.length > 1 && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!canDecide || decide.isPending}
                      onClick={() =>
                        decide.mutate({
                          key: c.key,
                          spellings,
                          action: 'apart',
                        })
                      }
                    >
                      Keep apart
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
          {r.clusters.length > 50 && (
            <p className="text-xs text-muted-foreground">
              Showing the 50 largest groups of {r.clusters.length}.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
