import { useId, type ReactNode } from 'react';

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

/** The CV's counties and sectors use the shared searchable multi-select (chips). */
export { MultiSelectField as ChipPicker } from '@/components/shared/multi-select-field';
