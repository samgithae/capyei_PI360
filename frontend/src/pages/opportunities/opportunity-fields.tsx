import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SelectField } from '@/components/shared/select-field';

export interface WhereWhat {
  sector_id: string | null;
  county_id: string | null;
  location: string;
  description: string;
  start_date: string | null;
}

interface Options {
  sectors: { id: string; name: string }[];
  counties: { id: string; name: string }[];
}

/** Industry, county, location and description: shared by Add and Edit so they cannot drift apart. */
export function WhereWhatFields({
  value,
  onChange,
  idPrefix,
}: {
  value: WhereWhat;
  onChange: (p: Partial<WhereWhat>) => void;
  idPrefix: string;
}) {
  const opts = useQuery({
    queryKey: ['employer-filters'],
    queryFn: () => api<Options>('/employers/filters'),
  });
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-start`}>Start date</Label>
          <Input
            id={`${idPrefix}-start`}
            type="date"
            value={value.start_date ?? ''}
            onChange={(e) => onChange({ start_date: e.target.value || null })}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Industry</Label>
          <SelectField
            label="Industry"
            className="w-full"
            emptyLabel="Not set"
            value={value.sector_id ?? ''}
            options={opts.data?.sectors ?? []}
            onChange={(x) => onChange({ sector_id: x || null })}
          />
        </div>
        <div className="space-y-1.5">
          <Label>County</Label>
          <SelectField
            label="County"
            className="w-full"
            emptyLabel="Not set"
            value={value.county_id ?? ''}
            options={opts.data?.counties ?? []}
            onChange={(x) => onChange({ county_id: x || null })}
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-location`}>Location</Label>
        <Input
          id={`${idPrefix}-location`}
          placeholder="Town, area or site"
          value={value.location}
          onChange={(e) => onChange({ location: e.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-description`}>Description</Label>
        <Textarea
          id={`${idPrefix}-description`}
          rows={4}
          value={value.description}
          onChange={(e) => onChange({ description: e.target.value })}
        />
      </div>
    </>
  );
}
