import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { SelectField } from '@/components/shared/select-field';

interface Row {
  id: string;
  name: string;
  active: boolean;
}

const list = (kind: string, param: string, parent: string) =>
  api<Row[]>(`/config/reference/${kind}?${param}=${parent}`);

/**
 * Sub-county and ward pickers that follow the chosen county. Values are stored as names
 * (the records keep text), so a place that is not in the list can still be typed.
 */
export function PlaceFields({
  countyId,
  subCounty,
  ward,
  onChange,
  showWard = true,
}: {
  countyId: string;
  subCounty: string;
  ward?: string;
  onChange: (patch: { subCounty?: string; ward?: string }) => void;
  showWard?: boolean;
}) {
  const subs = useQuery({
    queryKey: ['reference', 'sub-counties', 'of', countyId],
    queryFn: () => list('sub-counties', 'county', countyId),
    enabled: !!countyId,
  });
  const subRows = (subs.data ?? []).filter((s) => s.active);
  const subId = subRows.find((s) => s.name === subCounty)?.id ?? '';
  const wards = useQuery({
    queryKey: ['reference', 'wards', 'of', subId],
    queryFn: () => list('wards', 'sub_county', subId),
    enabled: !!subId,
  });
  const wardRows = (wards.data ?? []).filter((w) => w.active);

  const byName = (rows: Row[], current: string) => {
    const opts = rows.map((r) => ({ id: r.name, name: r.name }));
    // keep a typed or imported value visible even if it is not in the list
    return current && !rows.some((r) => r.name === current)
      ? [{ id: current, name: current }, ...opts]
      : opts;
  };

  return (
    <div className="grid grid-cols-2 gap-2">
      {subRows.length > 0 ? (
        <SelectField
          label="Sub-county"
          emptyLabel="Sub-county"
          className="w-full"
          value={subCounty}
          options={byName(subRows, subCounty)}
          onChange={(x) => onChange({ subCounty: x, ward: '' })}
        />
      ) : (
        <Input
          aria-label="Sub-county"
          placeholder="Sub-county"
          value={subCounty}
          onChange={(e) => onChange({ subCounty: e.target.value })}
        />
      )}
      {showWard &&
        (wardRows.length > 0 ? (
          <SelectField
            label="Ward"
            emptyLabel="Ward"
            className="w-full"
            value={ward ?? ''}
            options={byName(wardRows, ward ?? '')}
            onChange={(x) => onChange({ ward: x })}
          />
        ) : (
          <Input
            aria-label="Ward"
            placeholder="Ward"
            value={ward ?? ''}
            onChange={(e) => onChange({ ward: e.target.value })}
          />
        ))}
    </div>
  );
}
