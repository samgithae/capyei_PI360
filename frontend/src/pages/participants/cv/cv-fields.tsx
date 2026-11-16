import { useId, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { SelectField } from '@/components/shared/select-field';
import type { Opt } from './cv-types';

/** A label above one input, wired together so screen readers and tests can find the input. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children(id)}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/**
 * Searchable multi-select shown as removable chips. Used for counties and sectors; the options
 * come from the central lists, so nothing is typed free-hand.
 */
export function ChipPicker({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Opt[];
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  const left = options.filter((o) => !value.includes(o.id));
  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label={`Chosen: ${label}`}>
          {value.map((id) => {
            const name = options.find((o) => o.id === id)?.name ?? id;
            return (
              <li key={id}>
                <Badge variant="primary" appearance="light" className="gap-1">
                  {name}
                  <button
                    type="button"
                    aria-label={`Remove ${name}`}
                    className="rounded-full hover:text-destructive"
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
      <SelectField
        label={label}
        className="w-full sm:w-72"
        value=""
        options={left}
        onChange={(id) => id && onChange([...value, id])}
        disabled={left.length === 0}
      />
    </div>
  );
}
