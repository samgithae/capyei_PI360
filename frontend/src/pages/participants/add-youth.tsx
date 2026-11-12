import { useState, type ChangeEvent, type ReactNode } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ManageLink } from '@/components/shared/manage-link';
import { DialogShell } from '@/components/shared/modals';
import { PlaceFields } from '@/components/shared/place-fields';
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
interface ExtraRow {
  label: string;
  value: string;
  /** Added by hand (label editable and removable), as opposed to a standard import column. */
  custom?: boolean;
}

/** The extra columns the import keeps, under the same labels, so a youth added by hand looks
 * the same as one imported. */
const IMPORT_FIELDS = [
  'Sector',
  'TrainingCenter',
  'Organisation',
  'Org Physical Address',
  'Contact Person',
  'Contact Person PhoneNumber',
  'Placement Status',
  'Placement Date',
  'Benefits',
  'Designation',
];
const freshExtras = (): ExtraRow[] =>
  IMPORT_FIELDS.map((label) => ({ label, value: '' }));

const opts = (xs: string[]) => xs.map((x) => ({ id: x, name: x }));
const GENDERS = opts(['female', 'male', 'other', 'unknown']);
const STATUSES = opts(['active', 'completed', 'withdrawn', 'unknown']);
const ENROLLMENT = opts(['enrolled', 'completed', 'withdrawn', 'unknown']);
const STEPS = ['Identity', 'Home and contact', 'Enrollment', 'Review'];

const BLANK = {
  first: '',
  middle: '',
  last: '',
  gender: 'unknown',
  status: 'active',
  dob: '',
  phone: '',
  email: '',
  county: '',
  resCounty: '',
  subCounty: '',
  ward: '',
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
  const [extras, setExtras] = useState<ExtraRow[]>(freshExtras);
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
    setExtras(freshExtras());
    setStep(0);
    setError('');
    setMatches([]);
    setConfirmed(false);
  };

  const fullName = [v.first, v.middle, v.last]
    .map((x) => x.trim())
    .filter(Boolean)
    .join(' ');

  const body = () => ({
    full_name_source: fullName,
    given_name: v.first.trim(),
    family_name: v.last.trim(),
    other_names: v.middle.trim(),
    gender: v.gender,
    status: v.status,
    date_of_birth: v.dob || null,
    origin_county_id: v.county || null,
    residence: {
      county_id: v.resCounty || null,
      sub_county: v.subCounty.trim(),
      ward: v.ward.trim(),
    },
    contacts: [
      { kind: 'phone', value: v.phone.trim(), primary: true },
      { kind: 'email', value: v.email.trim(), primary: true },
    ].filter((c) => c.value),
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
          extras
            .filter((x) => x.label.trim() && x.value.trim())
            .map((x) => [x.label.trim(), x.value.trim()]),
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
    },
  });

  /** Checks that must pass before leaving a step. */
  const next = async () => {
    setError('');
    if (step === 0) {
      if (!v.first.trim() || !v.last.trim())
        return setError('First name and last name are required.');
      if (!confirmed) {
        try {
          const found = await api<{ matches: Match[] }>(
            `/participants/check-name?name=${encodeURIComponent(fullName)}`,
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
    if (step === 2 && v.cohort && !v.offering && can('config.view'))
      return setError('Choose a course for the cohort, or clear the cohort.');
    setStep((s) => s + 1);
  };

  const updateExtra = (i: number, patch: Partial<ExtraRow>) =>
    setExtras((r) => r.map((y, j) => (j === i ? { ...y, ...patch } : y)));

  if (!can('participants.edit')) return null;

  const countyName = (id: string) =>
    filters.data?.counties.find((c) => c.id === id)?.name ?? '';
  const summary: [string, string][] = [
    ['Name', fullName],
    ['Gender / status', `${v.gender} / ${v.status}`],
    ['Date of birth', v.dob],
    ['Home county', countyName(v.county)],
    [
      'Lives in',
      [countyName(v.resCounty), v.subCounty, v.ward].filter(Boolean).join(', '),
    ],
    ['Phone', v.phone],
    ['Email', v.email],
    [
      'Enrollment',
      v.offering
        ? `${filters.data?.cohorts.find((c) => c.id === v.cohort)?.name ?? ''} / ${offerings.data?.find((o) => o.id === v.offering)?.name ?? ''}`
        : 'None yet',
    ],
    [
      'Other details',
      String(extras.filter((x) => x.label.trim() && x.value.trim()).length),
    ],
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
              <div className="grid grid-cols-3 gap-2">
                {(['first', 'middle', 'last'] as const).map((k) =>
                  text(
                    k,
                    k === 'first'
                      ? 'First name'
                      : k === 'middle'
                        ? 'Middle name'
                        : 'Last name',
                    {
                      required: k !== 'middle',
                      onChange: (e: ChangeEvent<HTMLInputElement>) => {
                        set(k, e.target.value);
                        setMatches([]);
                        setConfirmed(false);
                      },
                    },
                  ),
                )}
              </div>
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
              {text('dob', 'Date of birth', { type: 'date' })}
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
                  onChange={(x) =>
                    setV((p) => ({
                      ...p,
                      resCounty: x,
                      subCounty: '',
                      ward: '',
                    }))
                  }
                />
                <PlaceFields
                  countyId={v.resCounty}
                  subCounty={v.subCounty}
                  ward={v.ward}
                  onChange={(p) => setV((x) => ({ ...x, ...p }))}
                />
              </div>
              {canContact && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Contact information</p>
                  <div className="grid grid-cols-2 gap-2">
                    {text('phone', 'Phone', {
                      type: 'tel',
                      placeholder: '07…',
                    })}
                    {text('email', 'Email', {
                      type: 'email',
                      placeholder: 'name@example.com',
                    })}
                  </div>
                </div>
              )}
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
              <ManageLink
                missing="Cohort or course"
                to="/administration/cohorts"
                label="Manage cohorts"
              />
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
                      Other details (same columns as the import)
                    </p>
                    {extras.map((x, i) => (
                      <div key={i} className="flex items-end gap-2">
                        {x.custom ? (
                          <Input
                            aria-label="Detail label"
                            placeholder="Label"
                            value={x.label}
                            onChange={(e) =>
                              updateExtra(i, { label: e.target.value })
                            }
                          />
                        ) : null}
                        <div className="flex-1">
                          {x.custom ? (
                            <Input
                              aria-label="Detail value"
                              placeholder="Value"
                              value={x.value}
                              onChange={(e) =>
                                updateExtra(i, { value: e.target.value })
                              }
                            />
                          ) : (
                            <Field label={x.label}>
                              <Input
                                aria-label={x.label}
                                type={
                                  x.label === 'Placement Date' ? 'date' : 'text'
                                }
                                value={x.value}
                                onChange={(e) =>
                                  updateExtra(i, { value: e.target.value })
                                }
                              />
                            </Field>
                          )}
                        </div>
                        {x.custom && (
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
                        )}
                      </div>
                    ))}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setExtras((r) => [
                          ...r,
                          { label: '', value: '', custom: true },
                        ])
                      }
                    >
                      <Plus /> Add another detail
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
