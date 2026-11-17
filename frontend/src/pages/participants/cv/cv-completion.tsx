import { useQuery } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, Pencil, Sparkles } from 'lucide-react';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { cvPaths, type CvDoc } from './cv-types';

/** Where the youth goes to finish their CV: the profile page, already on the edit view. */
export const COMPLETE_CV_PATH = '/me/profile?cv=edit#my-cv';

/** The youth's own CV document. Shares its cache entry with the CV on the profile page. */
export function useMyCv(enabled = true) {
  return useQuery({
    queryKey: ['participant-cv', 'self'],
    queryFn: () => api<CvDoc>(cvPaths('me', true).cv),
    retry: false,
    enabled,
  });
}

/** Colour and wording by how far along the CV is, so 40% reads differently from 90%. */
function tone(percent: number) {
  if (percent >= 100)
    return {
      bar: 'bg-success',
      box: 'border-success/30 bg-success/5',
      lead: 'Your CV is complete',
    };
  if (percent >= 70)
    return {
      bar: 'bg-primary',
      box: 'border-primary/30 bg-primary/5',
      lead: `Your CV is ${percent}% complete`,
    };
  return {
    bar: 'bg-warning',
    box: 'border-warning/40 bg-warning/5',
    lead: `Your CV is ${percent}% complete`,
  };
}

/**
 * "Your CV is 70% complete": what is still missing, in plain words, with one button that
 * opens the editor. `compact` is the one-line version for the dashboard.
 */
export function CvCompletion({
  cv,
  onEdit,
  linkToProfile = false,
  compact = false,
  self = true,
}: {
  cv: CvDoc;
  /** Opens the editor on the same page. */
  onEdit?: () => void;
  /** Links to the youth's profile page, already on the editor. Neither prop: no button. */
  linkToProfile?: boolean;
  compact?: boolean;
  self?: boolean;
}) {
  if (!cv.completeness) return null;
  const { percent, missing } = cv.completeness;
  const t = tone(percent);
  const done = percent >= 100;
  const lead = self ? t.lead : t.lead.replace('Your CV', 'This CV');
  const label = self ? 'Complete my CV' : 'Complete this CV';
  const action = onEdit ? (
    <Button size="md" onClick={onEdit} className="max-sm:w-full">
      <Pencil /> {label}
    </Button>
  ) : linkToProfile ? (
    <Button asChild size="md" className="max-sm:w-full">
      <Link to={COMPLETE_CV_PATH}>
        <Pencil /> {label}
      </Link>
    </Button>
  ) : null;

  const bar = (
    <div
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="CV profile completion"
      className="h-2.5 overflow-hidden rounded-full bg-muted"
    >
      <div
        className={cn('h-full rounded-full transition-all', t.bar)}
        style={{ width: `${percent}%` }}
      />
    </div>
  );

  if (compact) {
    if (done) return null;
    return (
      <section
        aria-label="CV profile completion"
        className={cn('space-y-3 rounded-lg border p-4', t.box)}
      >
        <div className="flex items-center gap-2">
          <AlertCircle className="size-5 shrink-0 text-warning" aria-hidden />
          <h2 className="font-semibold">{lead}</h2>
        </div>
        {bar}
        <p className="text-sm text-muted-foreground">
          {missing.length > 0
            ? `Still to add: ${missing.map((m) => m.label.toLowerCase()).join(', ')}.`
            : 'A few more details will make it stronger.'}
        </p>
        {action}
      </section>
    );
  }

  return (
    <section
      aria-label="CV profile completion"
      className={cn('space-y-4 rounded-lg border p-5', t.box)}
    >
      <div className="flex items-start gap-3">
        {done ? (
          <CheckCircle2 className="mt-0.5 size-6 shrink-0 text-success" />
        ) : (
          <Sparkles className="mt-0.5 size-6 shrink-0 text-warning" />
        )}
        <div className="min-w-0 flex-1 space-y-1">
          <h2 className="text-lg font-semibold">
            {lead}
            {done && ' 🎉'}
          </h2>
          <p className="text-sm text-muted-foreground">
            {done
              ? 'The essentials are in place. Adding more makes the CV stronger.'
              : self
                ? 'A complete CV helps your officer match you to the right opportunities. Finish these to get to 100%:'
                : 'Still missing from this CV:'}
          </p>
        </div>
        <span
          className="text-2xl font-semibold tabular-nums"
          aria-hidden="true"
        >
          {percent}%
        </span>
      </div>
      {bar}
      {!done && missing.length > 0 && (
        <ul className="space-y-2 text-sm">
          {missing.map((m) => (
            <li key={m.key} className="flex gap-2">
              <AlertCircle
                className="mt-0.5 size-4 shrink-0 text-warning"
                aria-hidden
              />
              <span>
                <span className="font-medium">{m.label}:</span>{' '}
                <span className="text-muted-foreground">{m.hint}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {!done && action}
    </section>
  );
}
