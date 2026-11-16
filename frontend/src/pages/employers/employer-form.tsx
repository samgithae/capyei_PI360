import { FormEvent, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ManageLink } from '@/components/shared/manage-link';
import { MultiSelectField } from '@/components/shared/multi-select-field';
import { PlaceFields } from '@/components/shared/place-fields';
import { SelectField } from '@/components/shared/select-field';

export interface Option {
  id: string;
  name: string;
}
/** `names(refs)` → "Mombasa, Nairobi" for lists and headers. */
export const names = (refs: Option[]) => refs.map((r) => r.name).join(', ');
export interface Options {
  sectors: Option[];
  counties: Option[];
}
export interface EmployerValues {
  name: string;
  sector_ids: string[];
  county_ids: string[];
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
  sector_ids: [],
  county_ids: [],
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
  const [v, setV] = useState(initial);
  const [matches, setMatches] = useState<Match[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k: keyof EmployerValues, val: string) =>
    setV((p) => ({ ...p, [k]: val }));
  // The sub-county is one place name, so it only makes sense for a single-county employer.
  // Changing the set of counties clears it rather than leaving one that belongs elsewhere.
  const setIds = (k: 'sector_ids' | 'county_ids', ids: string[]) =>
    setV((p) => ({
      ...p,
      [k]: ids,
      ...(k === 'county_ids' ? { sub_county: '' } : {}),
    }));

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
      <div className="space-y-1">
        <span className="text-sm font-medium">Industry / Sector</span>
        <MultiSelectField
          label="Add an industry / sector"
          options={options?.sectors ?? []}
          loading={!options}
          value={v.sector_ids}
          onChange={(ids) => setIds('sector_ids', ids)}
          emptyMessage="No industries / sectors are set up yet."
        />
        <ManageLink
          missing="Industry / Sector"
          to="/administration/sectors"
          label="Add or manage sectors"
        />
      </div>
      <div className="space-y-1">
        <span className="text-sm font-medium">Counties</span>
        <MultiSelectField
          label="Add a county"
          options={options?.counties ?? []}
          loading={!options}
          value={v.county_ids}
          onChange={(ids) => setIds('county_ids', ids)}
          emptyMessage="No counties are set up yet."
        />
      </div>
      <SelectField
        label="Status"
        className="w-44"
        value={v.status}
        options={['active', 'inactive', 'prospect'].map((s) => ({
          id: s,
          name: s,
        }))}
        onChange={(x) => set('status', x)}
      />
      {v.county_ids.length === 1 ? (
        <PlaceFields
          countyId={v.county_ids[0]}
          subCounty={v.sub_county}
          showWard={false}
          onChange={(p) =>
            p.subCounty !== undefined && set('sub_county', p.subCounty)
          }
        />
      ) : (
        v.county_ids.length > 1 && (
          <p className="text-xs text-muted-foreground">
            Sub-county is only recorded when the employer has one county.
          </p>
        )
      )}
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
