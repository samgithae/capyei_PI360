import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';

export interface ExportFieldGroup {
  key: string;
  label: string;
  fields: { key: string; label: string; sensitive: boolean }[];
}

/**
 * The field picker in the Export dialog: every field the table can hold, grouped by where it comes
 * from (the youth's own record, contact, address, project, education, work, readiness, referrals
 * and placements). The caller owns the selection; the dialog starts with everything ticked.
 */
export function ExportFields({
  groups,
  selected,
  onChange,
}: {
  groups: ExportFieldGroup[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const all = groups.flatMap((g) => g.fields.map((f) => f.key));
  const set = (keys: string[], on: boolean) => {
    const next = new Set(selected);
    for (const k of keys) {
      if (on) next.add(k);
      else next.delete(k);
    }
    onChange(next);
  };
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Label>Fields to include</Label>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-muted-foreground" aria-live="polite">
            {selected.size} of {all.length} selected
          </span>
          <button
            type="button"
            className="text-primary hover:underline"
            onClick={() => set(all, true)}
          >
            Select all
          </button>
          <button
            type="button"
            className="text-primary hover:underline"
            onClick={() => set(all, false)}
          >
            Clear
          </button>
        </div>
      </div>
      <div className="max-h-72 space-y-4 overflow-y-auto rounded-md border border-input p-3">
        {groups.map((g) => {
          const keys = g.fields.map((f) => f.key);
          const count = keys.filter((k) => selected.has(k)).length;
          return (
            <fieldset key={g.key} className="space-y-2">
              <legend className="sr-only">{g.label}</legend>
              <div className="flex items-center gap-2">
                <Checkbox
                  id={`export-group-${g.key}`}
                  size="sm"
                  checked={
                    count === keys.length
                      ? true
                      : count === 0
                        ? false
                        : 'indeterminate'
                  }
                  onCheckedChange={(v) => set(keys, v === true)}
                />
                <Label
                  htmlFor={`export-group-${g.key}`}
                  className="text-sm font-semibold"
                >
                  {g.label}
                </Label>
              </div>
              <div className="grid grid-cols-1 gap-x-4 gap-y-1.5 pl-6 sm:grid-cols-2">
                {g.fields.map((f) => (
                  <div key={f.key} className="flex items-center gap-2">
                    <Checkbox
                      id={`export-field-${f.key}`}
                      size="sm"
                      checked={selected.has(f.key)}
                      onCheckedChange={(v) => set([f.key], v === true)}
                    />
                    <Label
                      htmlFor={`export-field-${f.key}`}
                      className="text-sm font-normal"
                    >
                      {f.label}
                    </Label>
                    {f.sensitive && (
                      <span className="rounded bg-amber-100 px-1 text-[10px] font-medium text-amber-900">
                        Sensitive
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </fieldset>
          );
        })}
      </div>
    </div>
  );
}
