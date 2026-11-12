import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DataCard } from '@/components/data-card';
import { SelectField } from '@/components/shared/select-field';

export interface Contact {
  kind: 'phone' | 'email';
  value: string;
  primary: boolean;
}
export interface MyDetails {
  full_name: string;
  given_name: string;
  family_name: string;
  other_names: string;
  gender: string;
  date_of_birth: string | null;
  county_id: string;
  residence: { county_id: string; sub_county: string; ward: string };
  contacts: Contact[];
  counties: { id: string; name: string }[];
  genders: { value: string; label: string }[];
}

const NONE = '__none__';

/**
 * The details a youth may change themselves. Status, enrollment, officer and verification stay
 * with staff, and the e-mail used to sign in cannot be changed here.
 */
export function MyDetailsCard({ details }: { details: MyDetails }) {
  const qc = useQueryClient();
  const [d, setD] = useState<MyDetails>(details);
  const [error, setError] = useState('');
  const set = (p: Partial<MyDetails>) => setD((x) => ({ ...x, ...p }));
  const setContact = (i: number, p: Partial<Contact>) =>
    set({
      contacts: d.contacts.map((c, j) => (j === i ? { ...c, ...p } : c)),
    });
  const counties = [{ id: NONE, name: 'Not recorded' }, ...d.counties];

  const save = useMutation({
    mutationFn: () =>
      api('/youth/details', {
        method: 'PUT',
        body: JSON.stringify({
          full_name: d.full_name,
          given_name: d.given_name,
          family_name: d.family_name,
          other_names: d.other_names,
          gender: d.gender,
          date_of_birth: d.date_of_birth || null,
          county_id: d.county_id || null,
          residence: {
            county_id: d.residence.county_id || null,
            sub_county: d.residence.sub_county,
            ward: d.residence.ward,
          },
          contacts: d.contacts,
        }),
      }),
    onSuccess: () => {
      toast.success('Your details are saved.');
      void qc.invalidateQueries({ queryKey: ['youth-me'] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  const submit = () => {
    setError('');
    if (!d.full_name.trim()) return setError('Enter your full name.');
    if (d.contacts.some((c) => !c.value.trim()))
      return setError('Fill in or remove the empty contact.');
    save.mutate();
  };

  const text = (
    key: 'full_name' | 'given_name' | 'family_name' | 'other_names',
    label: string,
  ) => (
    <div className="space-y-1.5">
      <Label htmlFor={`my-${key}`}>{label}</Label>
      <Input
        id={`my-${key}`}
        value={d[key]}
        onChange={(e) => set({ [key]: e.target.value })}
      />
    </div>
  );

  return (
    <DataCard title="My details">
      <form
        className="space-y-5 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {text('full_name', 'Full name')}
        <div className="grid gap-4 sm:grid-cols-3">
          {text('given_name', 'First name')}
          {text('family_name', 'Middle name')}
          {text('other_names', 'Last name')}
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label>Gender</Label>
            <SelectField
              label="Gender"
              value={d.gender}
              options={d.genders.map((g) => ({ id: g.value, name: g.label }))}
              onChange={(x) => set({ gender: x })}
              className="capitalize"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="my-dob">Date of birth</Label>
            <Input
              id="my-dob"
              type="date"
              value={d.date_of_birth ?? ''}
              onChange={(e) => set({ date_of_birth: e.target.value || null })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Home county</Label>
            <SelectField
              label="Home county"
              value={d.county_id || NONE}
              options={counties}
              onChange={(x) => set({ county_id: x === NONE ? '' : x })}
            />
          </div>
        </div>

        <fieldset className="space-y-3 rounded-lg border border-border p-3">
          <legend className="px-1 text-sm font-medium">
            Where you live now
          </legend>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label>County</Label>
              <SelectField
                label="Residence county"
                value={d.residence.county_id || NONE}
                options={counties}
                onChange={(x) =>
                  set({
                    residence: {
                      ...d.residence,
                      county_id: x === NONE ? '' : x,
                    },
                  })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="my-sub">Sub-county</Label>
              <Input
                id="my-sub"
                value={d.residence.sub_county}
                onChange={(e) =>
                  set({
                    residence: { ...d.residence, sub_county: e.target.value },
                  })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="my-ward">Ward</Label>
              <Input
                id="my-ward"
                value={d.residence.ward}
                onChange={(e) =>
                  set({ residence: { ...d.residence, ward: e.target.value } })
                }
              />
            </div>
          </div>
        </fieldset>

        <fieldset className="space-y-3 rounded-lg border border-border p-3">
          <legend className="px-1 text-sm font-medium">How to reach you</legend>
          {d.contacts.map((c, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <div className="w-28">
                <SelectField
                  label="Contact type"
                  value={c.kind}
                  options={[
                    { id: 'phone', name: 'Phone' },
                    { id: 'email', name: 'E-mail' },
                  ]}
                  onChange={(x) =>
                    setContact(i, { kind: x as Contact['kind'] })
                  }
                />
              </div>
              <Input
                aria-label="Contact value"
                className="min-w-48 flex-1"
                value={c.value}
                onChange={(e) => setContact(i, { value: e.target.value })}
              />
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={c.primary}
                  onChange={(e) =>
                    set({
                      contacts: d.contacts.map((x, j) =>
                        j === i
                          ? { ...x, primary: e.target.checked }
                          : e.target.checked && x.kind === c.kind
                            ? { ...x, primary: false }
                            : x,
                      ),
                    })
                  }
                />
                Main
              </label>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Remove contact"
                onClick={() =>
                  set({ contacts: d.contacts.filter((_, j) => j !== i) })
                }
              >
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() =>
              set({
                contacts: [
                  ...d.contacts,
                  { kind: 'phone', value: '', primary: false },
                ],
              })
            }
          >
            <Plus /> Add contact
          </Button>
          <p className="text-xs text-muted-foreground">
            Changing an e-mail here does not change the e-mail you sign in with.
          </p>
        </fieldset>

        <p className="text-xs text-muted-foreground">
          Your status, course enrollment and assigned officer are kept by staff.
          Ask your officer if one of them is wrong.
        </p>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" disabled={save.isPending}>
          Save my details
        </Button>
      </form>
    </DataCard>
  );
}
