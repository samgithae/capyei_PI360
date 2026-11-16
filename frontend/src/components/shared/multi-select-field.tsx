import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { SelectField } from '@/components/shared/select-field';

export type MultiOption = { id: string; name: string };

/**
 * Searchable multi-select shown as removable chips. One component for every "pick several from a
 * central list" field: an employer's counties and sectors, an opportunity's counties and
 * sectors, a CV's preferences. The options always come from the central lists, so nothing is
 * typed free-hand and the same record can never be added twice.
 *
 * - `loading`: options are still being fetched (the picker is disabled and says so).
 * - `emptyMessage`: shown instead of the picker when there is nothing to choose from at all
 *   (for example an employer with no counties yet), so the user is told why and what to do.
 * - Chips of ids that are not in `options` (an old value, or an option still loading) are kept
 *   and shown by their id so they can be removed rather than silently dropped.
 */
export function MultiSelectField({
  label,
  options,
  value,
  onChange,
  labels = [],
  loading = false,
  emptyMessage,
  disabled = false,
  className = 'w-full sm:w-72',
}: {
  label: string;
  options: MultiOption[];
  value: string[];
  onChange: (ids: string[]) => void;
  /** Names for chosen ids that are not in `options` (old values), so chips never show raw ids. */
  labels?: MultiOption[];
  loading?: boolean;
  emptyMessage?: ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const left = options.filter((o) => !value.includes(o.id));
  const nothingToChoose = !loading && options.length === 0 && !!emptyMessage;
  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label={`Chosen: ${label}`}>
          {value.map((id) => {
            const name =
              options.find((o) => o.id === id)?.name ??
              labels.find((o) => o.id === id)?.name ??
              id;
            return (
              <li key={id}>
                <Badge variant="primary" appearance="light" className="gap-1">
                  {name}
                  <button
                    type="button"
                    aria-label={`Remove ${name}`}
                    disabled={disabled}
                    className="-m-1 rounded-full p-1 hover:text-destructive"
                    onClick={() => onChange(value.filter((v) => v !== id))}
                  >
                    <X className="size-3" />
                  </button>
                </Badge>
              </li>
            );
          })}
        </ul>
      )}
      {nothingToChoose ? (
        <p role="status" className="text-sm text-muted-foreground">
          {emptyMessage}
        </p>
      ) : (
        <SelectField
          label={loading ? 'Loading…' : label}
          className={className}
          value=""
          options={left}
          onChange={(id) => id && onChange([...value, id])}
          disabled={disabled || loading || left.length === 0}
        />
      )}
    </div>
  );
}
