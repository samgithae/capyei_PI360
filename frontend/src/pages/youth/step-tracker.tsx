import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { JourneyItem } from './journey';

/** The five steps of the journey. Steps already reached are ticked; the current one is bold.
 *  An ended referral (not selected, withdrawn) shows how far it got, with no step highlighted. */
export function StepTracker({
  steps,
  item,
}: {
  steps: { key: string; label: string }[];
  item: JourneyItem;
}) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {steps.map((s, i) => {
        const done = item.reached.includes(s.key);
        const current = !item.ended && item.stage === s.key;
        return (
          <li key={s.key} className="flex items-center gap-2">
            <span
              className={cn(
                'inline-flex size-5 items-center justify-center rounded-full border text-xs',
                done
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border text-muted-foreground',
              )}
            >
              {done ? <Check className="size-3" aria-hidden /> : i + 1}
            </span>
            <span
              className={cn(
                current ? 'font-semibold' : done ? '' : 'text-muted-foreground',
              )}
              aria-current={current ? 'step' : undefined}
            >
              {s.label}
            </span>
            {i < steps.length - 1 && (
              <span className="text-muted-foreground" aria-hidden>
                ›
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
