import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  MultiSelectField,
  type MultiOption,
} from '@/components/shared/multi-select-field';

export interface WhereWhat {
  sector_ids: string[];
  county_ids: string[];
  location: string;
  description: string;
  start_date: string | null;
  closing_date: string | null;
}

/**
 * Choosing another employer drops the picked counties and industries: they belong to the old
 * employer, so none may carry over. `cleared` says whether anything was dropped (to tell the user).
 */
export function switchEmployer<
  T extends { employer_id: string; county_ids: string[]; sector_ids: string[] },
>(v: T, employerId: string): { next: T; cleared: boolean } {
  if (employerId === v.employer_id) return { next: v, cleared: false };
  return {
    next: { ...v, employer_id: employerId, county_ids: [], sector_ids: [] },
    cleared: v.county_ids.length > 0 || v.sector_ids.length > 0,
  };
}

interface EmployerPlaces {
  counties: MultiOption[];
  sectors: MultiOption[];
}

/**
 * The counties and industries / sectors one employer works in. An opportunity may only use these,
 * so they are the only choices offered. Reloads whenever the employer changes.
 */
export function useEmployerPlaces(employerId: string, path?: string) {
  return useQuery({
    queryKey: ['employer', employerId, 'places', path ?? ''],
    queryFn: () => api<EmployerPlaces>(path ?? `/employers/${employerId}`),
    enabled: !!employerId,
  });
}

function EmptyForEmployer({
  what,
  employerId,
  href,
}: {
  what: string;
  employerId: string;
  href?: string;
}) {
  return (
    <>
      This employer has no {what} yet.{' '}
      <Link
        to={href ?? `/employers/${employerId}`}
        className="text-primary underline"
      >
        Add them on the employer profile
      </Link>{' '}
      first.
    </>
  );
}

function Outside({ names, noun }: { names: string[]; noun: string }) {
  if (names.length === 0) return null;
  return (
    <p role="alert" className="text-xs text-destructive">
      {names.join(', ')} {names.length === 1 ? 'is' : 'are'} not among this
      employer&rsquo;s {noun}. Remove {names.length === 1 ? 'it' : 'them'}, or
      add {names.length === 1 ? 'it' : 'them'} to the employer profile.
    </p>
  );
}

/**
 * Start date, closing date, industry / sector, counties, location and description, shared by Add and Edit so
 * they cannot drift apart. Employer → available counties → industry / sector: with no employer
 * chosen both pickers are disabled and say why; with one chosen they list only its own.
 * `stored` names values the opportunity already holds, so an older one that the employer no
 * longer lists still shows by name (and is flagged) instead of vanishing.
 */
export function WhereWhatFields({
  value,
  onChange,
  idPrefix,
  employerId,
  stored,
  placesPath,
  profileHref,
}: {
  value: WhereWhat;
  onChange: (p: Partial<WhereWhat>) => void;
  idPrefix: string;
  employerId: string;
  stored?: EmployerPlaces;
  /** Where the company's counties and industries are read from. The employer portal passes
   * its own profile route, so the staff-only employer record is never requested. */
  placesPath?: string;
  /** Where "add them on the profile" points. Defaults to the staff employer page. */
  profileHref?: string;
}) {
  const places = useEmployerPlaces(employerId, placesPath);
  const counties = places.data?.counties ?? [];
  const sectors = places.data?.sectors ?? [];
  const nameOf = (rows: MultiOption[], extra: MultiOption[], id: string) =>
    rows.find((r) => r.id === id)?.name ??
    extra.find((r) => r.id === id)?.name ??
    id;
  const outside = (
    chosen: string[],
    allowed: MultiOption[],
    extra: MultiOption[] | undefined,
  ) =>
    places.data
      ? chosen
          .filter((id) => !allowed.some((a) => a.id === id))
          .map((id) => nameOf(allowed, extra ?? [], id))
      : [];
  const pick = (what: string, noun: string): ReactNode =>
    !employerId ? (
      `Choose an employer first to pick its ${noun}.`
    ) : (
      <EmptyForEmployer
        what={what}
        employerId={employerId}
        href={profileHref}
      />
    );
  return (
    <>
      {!employerId && (
        <p className="text-xs text-muted-foreground">
          Industry / Sector and Counties come from the employer you choose.
        </p>
      )}
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
          <Label htmlFor={`${idPrefix}-closing`}>Closing date</Label>
          <Input
            id={`${idPrefix}-closing`}
            type="date"
            value={value.closing_date ?? ''}
            onChange={(e) => onChange({ closing_date: e.target.value || null })}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Industry / Sector</Label>
          <MultiSelectField
            label="Add an industry / sector"
            className="w-full"
            options={sectors}
            labels={stored?.sectors}
            value={value.sector_ids}
            loading={!!employerId && places.isPending}
            disabled={!employerId}
            emptyMessage={pick('industries / sectors', 'industries / sectors')}
            onChange={(ids) => onChange({ sector_ids: ids })}
          />
          <Outside
            names={outside(value.sector_ids, sectors, stored?.sectors)}
            noun="industries / sectors"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Counties</Label>
          <MultiSelectField
            label="Add a county"
            className="w-full"
            options={counties}
            labels={stored?.counties}
            value={value.county_ids}
            loading={!!employerId && places.isPending}
            disabled={!employerId}
            emptyMessage={pick('counties', 'counties')}
            onChange={(ids) => onChange({ county_ids: ids })}
          />
          <Outside
            names={outside(value.county_ids, counties, stored?.counties)}
            noun="counties"
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
