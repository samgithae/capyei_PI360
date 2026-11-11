import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// Radix Select cannot hold an empty-string value, so "none chosen" uses this sentinel.
const NONE = '__none__';

/** Metronic Select with plain string in/out; `emptyLabel` adds a "none" option that maps to ''. */
export function SelectField({
  label,
  value,
  options,
  onChange,
  emptyLabel,
  className,
}: {
  label: string;
  value: string;
  options: { id: string; name: string }[];
  onChange: (value: string) => void;
  emptyLabel?: string;
  className?: string;
}) {
  return (
    <Select
      value={value || (emptyLabel ? NONE : '')}
      onValueChange={(v) => onChange(v === NONE ? '' : v)}
    >
      <SelectTrigger aria-label={label} className={className}>
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        {emptyLabel && <SelectItem value={NONE}>{emptyLabel}</SelectItem>}
        {options.map((o) => (
          <SelectItem key={o.id} value={o.id}>
            {o.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
