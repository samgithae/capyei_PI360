import { useState, type ChangeEvent, type ReactNode } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DialogShell } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';

interface Option {
  id: string;
  name: string;
}
interface Filters {
  cohorts: Option[];
  counties: Option[];
}
interface Match {
  id: string;
  name: string;
  status: string;
}
interface ContactRow {
  kind: 'phone' | 'email';
  value: string;
  primary: boolean;
}
interface ExtraRow {
  label: string;
  value: string;
}

const opts = (xs: string[]) => xs.map((x) => ({ id: x, name: x }));
const GENDERS = opts(['female', 'male', 'other', 'unknown']);
const STATUSES = opts(['active', 'completed', 'withdrawn', 'unknown']);
const ENROLLMENT = opts(['enrolled', 'completed', 'withdrawn', 'unknown']);
const STEPS = ['Identity', 'Home and contact', 'Enrollment', 'Review'];

const BLANK = {
  name: '',
  given: '',
  family: '',
  other: '',
  gender: 'unknown',
  status: 'active',
  dob: '',
  age: '',
  ageBasis: '',
  county: '',
  resCounty: '',
  subCounty: '',
  ward: '',
  sourceName: '',
  sourceId: '',
  cohort: '',
  offering: '',
  enrollmentNo: '',
  enrollStatus: 'enrolled',
  enrolledOn: '',
  completedOn: '',
  exitReason: '',
  qualification: '',
  referralSource: '',
};
type Values = typeof BLANK;

const Field = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="space-y-1.5">
    <Label>{label}</Label>
    {children}
  </div>
);

/** "Add youth": a four-step wizard covering every detail the directory holds. Only the name is
 * required; everything else can be left blank and added later from the profile. */
export function AddYouth() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const canContact = can('participants.view_contact');
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [v, setV] = useState<Values>(BLANK);
  const [contacts, setContacts] = useState<ContactRow[]>([]);
  const [extras, setExtras] = useState<ExtraRow[]>([]);
  const [error, setError] = useState('');
  const [matches, setMatches] = useState<Match[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const set = (k: keyof Values, val: string) =>
    setV((p) => ({ ...p, [k]: val }));
  const text = (
    k: keyof Values,
    label: string,
    props: React.ComponentProps<typeof Input> = {},
  ) => (
    <Field label={label}>
      <Input
        aria-label={label}
        value={v[k]}
        onChange={(e) => set(k, e.target.value)}
        {...props}
      />
    </Field>
  );

  const filters = useQuery({
    queryKey: ['participant-filters'],
    queryFn: () => api<Filters>('/participants/filters'),
    enabled: open,
  });
  const offerings = useQuery({
    queryKey: ['offerings', v.cohort],
    queryFn: async () => {
      const [cc, courses] = await Promise.all([
        api<{ id: string; course: string }[]>(
          `/config/reference/cohort-courses?cohort=${v.cohort}&active=true`,
        ),
        api<Option[]>('/config/reference/courses'),
      ]);
      const name = new Map(courses.map((c) => [c.id, c.name]));
      return cc.map((o) => ({
        id: o.id,
        name: name.get(o.course) ?? 'Course',
      }));
    },
    enabled: open && !!v.cohort && can('config.view'),
  });

  const reset = () => {
    setV(BLANK);
    setContacts([]);
    setExtras([]);
    setStep(0);
    setError('');
    setMatches([]);
    setConfirmed(false);
  };

  const body = () => ({
    full_name_source: v.name.trim(),
    given_name: v.given.trim(),
    family_name: v.family.trim(),
    other_names: v.other.trim(),
    gender: v.gender,
    status: v.status,
    date_of_birth: v.dob || null,
    age_at_source: v.age === '' ? null : Number(v.age),
    age_basis_date: v.ageBasis || null,
    origin_county_id: v.county || null,
    residence: {
      county_id: v.resCounty || null,
      sub_county: v.subCounty.trim(),
      ward: v.ward.trim(),
    },
    contacts: contacts
      .filter((c) => c.value.trim())
      .map((c) => ({ ...c, value: c.value.trim() })),
    source_name: v.sourceName.trim(),
    source_id: v.sourceId.trim(),
    ...(v.offering && {
      enrollment: {
        cohort_course_id: v.offering,
        enrollment_no: v.enrollmentNo.trim(),
        status: v.enrollStatus,
        enrolled_on: v.enrolledOn || null,
        completed_on: v.completedOn || null,
        exit_reason: v.exitReason.trim(),
        qualification_code: v.qualification.trim(),
        referral_source_code: v.referralSource.trim(),
        extra: Object.fromEntries(
          extras.filter((x) => x.label.trim()).map((x) => [x.label, x.value]),
        ),
      },
    }),
  });

  const create = useMutation({
    mutationFn: () => post<{ id: string }>('/participants', body()),
    onSuccess: (p) => {
      toast.success('Youth added');
      setOpen(false);
      reset();
      void qc.invalidateQueries({ queryKey: ['participants'] });
      navigate(`/youth/${p.id}`);
    },
    onError: (e) => {
      const m = e instanceof ApiError ? e.message : 'Could not save.';
      setError(m);
      // send the user back to the step that holds the problem
      if (/number|enrollment|course/i.test(m)) setStep(2);
      else if (/ID|system/i.test(m)) setStep(1);
    },
  });

  /** Checks that must pass before leaving a step. */
  const next = async () => {
    setError('');
    if (step === 0) {
      if (!v.name.trim()) return setError('A name is required.');
      if (!confirmed) {
        try {
          const found = await api<{ matches: Match[] }>(
            `/participants/check-name?name=${encodeURIComponent(v.name.trim())}`,
          );
          if (found.matches.length) {
            setMatches(found.matches);
            return;
          }
        } catch {
          /* a courtesy check; saving still validates */
        }
      }
    }
    if (step === 1 && v.sourceId.trim() && !v.sourceName.trim())
      return setError('Say which system the ID is from.');
    if (step === 2 && v.cohort && !v.offering && can('config.view'))
      return setError('Choose a course for the cohort, or clear the cohort.');
    setStep((s) => s + 1);
  };

  const updateContact = (i: number, patch: Partial<ContactRow>) =>
    setContacts((r) => r.map((y, j) => (j === i ? { ...y, ...patch } : y)));
  const updateExtra = (i: number, patch: Partial<ExtraRow>) =>
    setExtras((r) => r.map((y, j) => (j === i ? { ...y, ...patch } : y)));

  if (!can('participants.edit')) return null;

  const countyName = (id: string) =>
    filters.data?.counties.find((c) => c.id === id)?.name ?? '';
  const summary: [string, string][] = [
    ['Name', v.name],
    ['Gender / status', `${v.gender} / ${v.status}`],
    ['Date of birth', v.dob],
    ['Age', v.age ? `${v.age}${v.ageBasis ? ` (on ${v.ageBasis})` : ''}` : ''],
    ['Home county', countyName(v.county)],
    [
      'Lives in',
      [countyName(v.resCounty), v.subCounty, v.ward].filter(Boolean).join(', '),
    ],
    ['Contacts', String(contacts.filter((c) => c.value.trim()).length)],
    ['Source ID', v.sourceId ? `${v.sourceName}: ${v.sourceId}` : ''],
    [
      'Enrollment',
      v.offering
        ? `${filters.data?.cohorts.find((c) => c.id === v.cohort)?.name ?? ''} / ${offerings.data?.find((o) => o.id === v.offering)?.name ?? ''}`
        : 'None yet',
    ],
    ['Other details', String(extras.filter((x) => x.label.trim()).length)],
  ];

  return (
    <>
      <Button
        onClick={() => {
          reset();
          setOpen(true);
        }}
      >
        Add youth
      </Button>
      <DialogShell
        open={open}
        onOpenChange={setOpen}
        title="Add youth"
        description="Add one youth by hand. To add many at once, use Import participants."
      >
        <ol className="mb-4 flex gap-2 text-xs">
          {STEPS.map((s, i) => (
            <li
              key={s}
              className={`flex-1 border-b-2 pb-1 ${
                i === step
                  ? 'border-primary font-semibold text-foreground'
                  : i < step
                    ? 'border-primary/40 text-muted-foreground'
                    : 'border-border text-muted-foreground'
              }`}
            >
              {i + 1}. {s}
            </li>
          ))}
        </ol>

        <div className="space-y-4">
          {step === 0 && (
            <>
              {text('name', 'Full name (as on the source sheet)', {
                required: true,
                onChange: (e: ChangeEvent<HTMLInputElement>) => {
                  set('name', e.target.value);
                  setMatches([]);
                  setConfirmed(false);
                },
              })}
              {matches.length > 0 && (
                <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
                  Someone with this name is already in the directory:{' '}
                  {matches.map((m) => `${m.name} (${m.status})`).join(', ')}. If
                  this is a different person,{' '}
                  <button
                    type="button"
                    className="font-medium underline"
                    onClick={() => {
                      setConfirmed(true);
                      setMatches([]);
                      setStep(1);
                    }}
                  >
                    continue anyway
                  </button>
                  .
                </div>
              )}
              <div className="grid grid-cols-3 gap-2">
                {text('given', 'Given name')}
                {text('family', 'Family name')}
                {text('other', 'Other names')}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Gender">
                  <SelectField
                    label="Gender"
                    className="w-full capitalize"
                    value={v.gender}
                    options={GENDERS}
                    onChange={(x) => set('gender', x)}
                  />
                </Field>
                <Field label="Status">
                  <SelectField
                    label="Status"
                    className="w-full capitalize"
                    value={v.status}
                    options={STATUSES}
                    onChange={(x) => set('status', x)}
                  />
                </Field>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {text('dob', 'Date of birth', { type: 'date' })}
                {text('age', 'Age', { type: 'number', min: 0, max: 120 })}
                {text('ageBasis', 'Age stated on', { type: 'date' })}
              </div>
              <p className="text-xs text-muted-foreground">
                Sources usually give an age, not a birth date. Fill in whichever
                you have; “Age stated on” is the date that age was true.
              </p>
            </>
          )}

          {step === 1 && (
            <>
              <Field label="Home county (where they come from)">
                <SelectField
                  label="Home county"
                  emptyLabel="Unknown"
                  className="w-full"
                  value={v.county}
                  options={filters.data?.counties ?? []}
                  onChange={(x) => set('county', x)}
                />
              </Field>
              <div className="space-y-2">
                <p className="text-sm font-medium">Where they live now</p>
                <SelectField
                  label="Residence county"
                  emptyLabel="County unknown"
                  className="w-full"
                  value={v.resCounty}
                  options={filters.data?.counties ?? []}
                  onChange={(x) => set('resCounty', x)}
                />
                <div className="grid grid-cols-2 gap-2">
                  {text('subCounty', 'Sub-county')}
                  {text('ward', 'Ward')}
                </div>
              </div>
              {canContact && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Contact details</p>
                  {contacts.map((c, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <SelectField
                        label="Contact type"
                        className="w-28 capitalize"
                        value={c.kind}
                        options={opts(['phone', 'email'])}
                        onChange={(x) =>
                          updateContact(i, { kind: x as ContactRow['kind'] })
                        }
                      />
                      <Input
                        aria-label="Contact value"
                        placeholder={
                          c.kind === 'phone' ? '07…' : 'name@example.com'
                        }
                        value={c.value}
                        onChange={(e) =>
                          updateContact(i, { value: e.target.value })
                        }
                      />
                      <label className="flex items-center gap-1 text-xs whitespace-nowrap">
                        <Checkbox
                          checked={c.primary}
                          onCheckedChange={(on) =>
                            setContacts((r) =>
                              r.map((y, j) =>
                                j === i
                                  ? { ...y, primary: on === true }
                                  : y.kind === c.kind && on === true
                                    ? { ...y, primary: false }
                                    : y,
                              ),
                            )
                          }
                        />
                        Primary
                      </label>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label="Remove contact"
                        onClick={() =>
                          setContacts((r) => r.filter((_, j) => j !== i))
                        }
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setContacts((r) => [
                        ...r,
                        {
                          kind: 'phone',
                          value: '',
                          primary: !r.some((x) => x.kind === 'phone'),
                        },
                      ])
                    }
                  >
                    <Plus /> Add phone or email
                  </Button>
                </div>
              )}
              <div className="space-y-2">
                <p className="text-sm font-medium">
                  ID in another system (optional)
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {text('sourceName', 'System name, e.g. KCB sheet')}
                  {text('sourceId', 'ID in that system')}
                </div>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <p className="text-sm text-muted-foreground">
                Optional. Leave the cohort empty to add the youth without an
                enrollment.
              </p>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Cohort">
                  <SelectField
                    label="Cohort"
                    emptyLabel="No cohort yet"
                    className="w-full"
                    value={v.cohort}
                    options={filters.data?.cohorts ?? []}
                    onChange={(x) =>
                      setV((p) => ({ ...p, cohort: x, offering: '' }))
                    }
                  />
                </Field>
                {v.cohort && (
                  <Field label="Course">
                    <SelectField
                      label="Course"
                      className="w-full"
                      value={v.offering}
                      options={offerings.data ?? []}
                      onChange={(x) => set('offering', x)}
                    />
                  </Field>
                )}
              </div>
              {v.offering && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    {text('enrollmentNo', 'Enrollment number')}
                    <Field label="Enrollment status">
                      <SelectField
                        label="Enrollment status"
                        className="w-full capitalize"
                        value={v.enrollStatus}
                        options={ENROLLMENT}
                        onChange={(x) => set('enrollStatus', x)}
                      />
                    </Field>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {text('enrolledOn', 'Enrolled on', { type: 'date' })}
                    {text('completedOn', 'Completed on', { type: 'date' })}
                  </div>
                  {text('exitReason', 'Exit reason (if they left)')}
                  <div className="grid grid-cols-2 gap-2">
                    {text('qualification', 'Qualification code')}
                    {text('referralSource', 'Referral source code')}
                  </div>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">
                      Other details from the source sheet
                    </p>
                    {extras.map((x, i) => (
                      <div key={i} className="flex gap-2">
                        <Input
                          aria-label="Detail label"
                          placeholder="Label"
                          value={x.label}
                          onChange={(e) =>
                            updateExtra(i, { label: e.target.value })
                          }
                        />
                        <Input
                          aria-label="Detail value"
                          placeholder="Value"
                          value={x.value}
                          onChange={(e) =>
                            updateExtra(i, { value: e.target.value })
                          }
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label="Remove detail"
                          onClick={() =>
                            setExtras((r) => r.filter((_, j) => j !== i))
                          }
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    ))}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setExtras((r) => [...r, { label: '', value: '' }])
                      }
                    >
                      <Plus /> Add a detail
                    </Button>
                  </div>
                </>
              )}
            </>
          )}

          {step === 3 && (
            <dl className="grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1.5 text-sm">
              {summary.map(([k, val]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd>{val || '—'}</dd>
                </div>
              ))}
            </dl>
          )}

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex justify-between pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => (step === 0 ? setOpen(false) : setStep(step - 1))}
            >
              {step === 0 ? 'Cancel' : 'Back'}
            </Button>
            {step < 3 ? (
              <Button type="button" onClick={() => void next()}>
                Next
              </Button>
            ) : (
              <Button
                type="button"
                disabled={create.isPending}
                onClick={() => create.mutate()}
              >
                {create.isPending ? 'Saving...' : 'Add youth'}
              </Button>
            )}
          </div>
        </div>
      </DialogShell>
    </>
  );
}
