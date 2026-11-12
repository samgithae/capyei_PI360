import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, X } from 'lucide-react';
import { toast } from 'sonner';
import { ApiError, post } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';

interface Ref {
  id: string;
  name?: string;
  code?: string;
  active: boolean;
  programme?: unknown;
  [k: string]: unknown;
}

/**
 * Add cohort courses in bulk: pick one cohort, then tap every course it runs.
 * Courses from the cohort's own programme come first; others stay available
 * and are labelled with their programme.
 */
export function LinkCoursesDialog({
  open,
  onOpenChange,
  cohorts,
  courses,
  programmes,
  links,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cohorts: Ref[];
  courses: Ref[];
  programmes: Ref[];
  /** Existing cohort-course records, so already-offered courses are shown as such. */
  links: Ref[];
  onDone: () => void;
}) {
  const [cohort, setCohort] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [find, setFind] = useState('');
  const [error, setError] = useState('');

  const close = (o: boolean) => {
    if (!o) {
      setCohort('');
      setPicked([]);
      setFind('');
      setError('');
    }
    onOpenChange(o);
  };

  const programmeName = (id: unknown) =>
    programmes.find((p) => p.id === id)?.name ?? '';
  const chosen = cohorts.find((c) => c.id === cohort);
  const offered = new Set(
    links.filter((l) => l.cohort === cohort && l.active).map((l) => l.course),
  );
  const q = find.trim().toLowerCase();
  const usable = courses
    .filter((c) => c.active)
    .filter((c) => !q || (c.name ?? '').toLowerCase().includes(q));
  const own = usable.filter((c) => c.programme === chosen?.programme);
  const other = usable.filter((c) => c.programme !== chosen?.programme);

  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const save = useMutation({
    mutationFn: () =>
      post<{ added: number; already_linked: number }>(
        '/config/reference/cohort-courses/bulk',
        { cohort, courses: picked },
      ),
    onSuccess: (r) => {
      toast.success(
        r.added === 1 ? '1 course added' : `${r.added} courses added`,
      );
      onDone();
      close(false);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  const pill = (c: Ref) => {
    const already = offered.has(c.id);
    const on = picked.includes(c.id);
    return (
      <button
        key={c.id}
        type="button"
        disabled={already}
        aria-pressed={already || on}
        onClick={() => toggle(c.id)}
        className={cn(
          'inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm transition-colors',
          on && 'border-primary bg-primary text-primary-foreground',
          !on && !already && 'border-border hover:bg-muted',
          already &&
            'cursor-not-allowed border-border bg-muted/50 text-muted-foreground',
        )}
      >
        {(on || already) && <Check className="size-3.5" />}
        {c.name}
        {already && <span className="text-xs"> (already added)</span>}
      </button>
    );
  };

  return (
    <FormModal
      open={open}
      onOpenChange={close}
      title="Add cohort courses"
      description="Choose a cohort, then tap each course it runs."
      submitLabel={
        picked.length > 1 ? `Add ${picked.length} courses` : 'Add course'
      }
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!cohort) return setError('Choose a cohort.');
        if (picked.length === 0) return setError('Choose at least one course.');
        setError('');
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label>Cohort *</Label>
        <SelectField
          label="Cohort"
          className="w-full"
          value={cohort}
          options={cohorts
            .filter((c) => c.active)
            .map((c) => ({
              id: c.id,
              name: `${c.name} (${programmeName(c.programme) || c.code})`,
            }))}
          onChange={(v) => {
            setCohort(v);
            setPicked([]);
          }}
        />
      </div>

      {cohort && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Courses *</Label>
            <Input
              aria-label="Find a course"
              placeholder="Find a course…"
              value={find}
              onChange={(e) => setFind(e.target.value)}
            />
          </div>
          {picked.length > 0 && (
            <p className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
              Selected:
              {picked.map((id) => (
                <button
                  key={id}
                  type="button"
                  aria-label={`Remove ${courses.find((c) => c.id === id)?.name}`}
                  onClick={() => toggle(id)}
                  className="inline-flex items-center gap-0.5 rounded-full bg-muted px-2 py-0.5 text-foreground"
                >
                  {courses.find((c) => c.id === id)?.name}
                  <X className="size-3" />
                </button>
              ))}
            </p>
          )}
          <div className="max-h-64 space-y-3 overflow-y-auto">
            <div>
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                {programmeName(chosen?.programme) || 'This programme'}
              </p>
              <div className="flex flex-wrap gap-2">
                {own.length ? (
                  own.map(pill)
                ) : (
                  <span className="text-xs text-muted-foreground">
                    No courses in this programme yet.
                  </span>
                )}
              </div>
            </div>
            {other.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                  Other programmes
                </p>
                <div className="flex flex-wrap gap-2">
                  {other.map((c) => (
                    <span key={c.id} title={programmeName(c.programme)}>
                      {pill(c)}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </FormModal>
  );
}
