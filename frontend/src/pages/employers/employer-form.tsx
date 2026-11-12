import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { Link } from 'react-router';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SelectField } from '@/components/shared/select-field';

export interface Option {
  id: string;
  name: string;
}
export interface Options {
  sectors: Option[];
  counties: Option[];
}
export interface EmployerValues {
  name: string;
  sector_id: string | null;
  county_id: string | null;
  sub_county: string;
  address: string;
  website: string;
  status: string;
  notes: string;
}
interface Match {
  id: string;
  name: string;
  status: string;
}

export const EMPTY: EmployerValues = {
  name: '',
  sector_id: null,
  county_id: null,
  sub_county: '',
  address: '',
  website: '',
  status: 'active',
  notes: '',
};

/** Create/edit form. Warns about similar names before saving; the user may confirm anyway. */
export function EmployerForm({
  initial,
  employerId,
  options,
  onSave,
  onCancel,
}: {
  initial: EmployerValues;
  employerId?: string;
  options?: Options;
  onSave: (values: EmployerValues, confirmDuplicate: boolean) => Promise<void>;
  onCancel?: () => void;
}) {
  const { can } = useAuth();
  const [v, setV] = useState(initial);
  const [matches, setMatches] = useState<Match[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k: keyof EmployerValues, val: string) =>
    setV((p) => ({ ...p, [k]: val === '' && k.endsWith('_id') ? null : val }));

  const submit = async (e: FormEvent, confirm = false) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (!confirm && v.name.trim() && v.name.trim() !== initial.name) {
        const q = new URLSearchParams({ name: v.name });
        if (employerId) q.set('exclude', employerId);
        const found = await api<{ matches: Match[] }>(
          `/employers/check-name?${q}`,
        );
        if (found.matches.length) {
          setMatches(found.matches);
          return;
        }
      }
      await onSave(v, confirm);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save.');
    } finally {
      setBusy(false);
    }
  };

  const select = (
    k: 'sector_id' | 'county_id' | 'status',
    label: string,
    items: Option[],
  ) => (
    <SelectField
      label={label}
      className="w-44"
      value={v[k] ?? ''}
      emptyLabel={k !== 'status' ? label : undefined}
      options={items}
      onChange={(x) => set(k, x)}
    />
  );

  return (
    <form onSubmit={submit} className="space-y-3">
      <Input
        aria-label="Employer name"
        placeholder="Employer name"
        value={v.name}
        onChange={(e) => {
          set('name', e.target.value);
          setMatches([]);
        }}
        required
      />
      <div className="flex flex-wrap gap-2">
        {select('sector_id', 'Sector', options?.sectors ?? [])}
        {select('county_id', 'County', options?.counties ?? [])}
        {select(
          'status',
          'Status',
          ['active', 'inactive', 'prospect'].map((s) => ({ id: s, name: s })),
        )}
      </div>
      {can('reference.manage') && (
        <p className="text-xs text-muted-foreground">
          Sector missing?{' '}
          <Link
            to="/administration/sectors"
            className="text-primary underline"
            target="_blank"
          >
            Add or manage sectors
          </Link>{' '}
          (opens in a new tab, then reopen this form).
        </p>
      )}
      <Input
        aria-label="Sub-county"
        placeholder="Sub-county"
        value={v.sub_county}
        onChange={(e) => set('sub_county', e.target.value)}
      />
      <Input
        aria-label="Address"
        placeholder="Address"
        value={v.address}
        onChange={(e) => set('address', e.target.value)}
      />
      <Input
        aria-label="Website"
        placeholder="Website"
        value={v.website}
        onChange={(e) => set('website', e.target.value)}
      />
      <Input
        aria-label="Notes"
        placeholder="Notes"
        value={v.notes}
        onChange={(e) => set('notes', e.target.value)}
      />
      {matches.length > 0 && (
        <div role="alert" className="rounded-md border p-3 text-sm">
          <p className="font-medium">A similar employer already exists:</p>
          <ul className="list-disc pl-5">
            {matches.map((m) => (
              <li key={m.id}>
                {m.name} ({m.status})
              </li>
            ))}
          </ul>
          <Button
            type="button"
            variant="outline"
            className="mt-2"
            disabled={busy}
            onClick={(e) => void submit(e, true)}
          >
            Save anyway
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={busy || matches.length > 0}>
          Save
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
