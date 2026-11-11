import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';
import { ErrorState, LoadingState } from '@/components/states';

interface Enrollment {
  id: string;
  programme: string;
  cohort: string;
  course: string;
  enrollment_no: string;
  status: string;
  enrolled_on: string | null;
  completed_on: string | null;
  exit_reason: string;
}
interface Detail {
  name: string;
  given_name: string;
  family_name: string;
  other_names: string;
  gender: string;
  status: string;
  date_of_birth: string | null;
  age_at_source: number | null;
  county_id: string;
  enrollments: Enrollment[];
}
interface Filters {
  counties: { id: string; name: string }[];
}

const GENDERS = ['female', 'male', 'other', 'unknown'];
const STATUSES = ['active', 'completed', 'withdrawn', 'unknown'];
const ENROLLMENT = ['enrolled', 'completed', 'withdrawn', 'unknown'];
const opts = (xs: string[]) => xs.map((x) => ({ id: x, name: x }));
const NO_COUNTY = 'none'; // Radix Select cannot hold an empty value

type Core = Omit<Detail, 'enrollments'>;
type EnrollmentDraft = Record<string, Partial<Enrollment>>;

/** Edit everything about a participant the API allows: identity, demographics and each enrollment. */
export function EditParticipant({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ['participant', id],
    queryFn: () => api<Detail>(`/participants/${id}`),
  });
  const filters = useQuery({
    queryKey: ['participant-filters'],
    queryFn: () => api<Filters>('/participants/filters'),
  });
  const [core, setCore] = useState<Partial<Core>>({});
  const [enr, setEnr] = useState<EnrollmentDraft>({});
  const [error, setError] = useState('');
  const d = detail.data;
  const v = d ? { ...d, ...core } : null;
  const patchEnr = (eid: string, p: Partial<Enrollment>) =>
    setEnr((x) => ({ ...x, [eid]: { ...x[eid], ...p } }));

  const save = useMutation({
    mutationFn: async () => {
      if (!d) return;
      // Send only what changed, so untouched blanks on imported records stay as they are.
      if (Object.keys(core).length > 0) {
        const body: Record<string, unknown> = { ...core };
        if ('county_id' in core) {
          body.origin_county_id = core.county_id || null;
          delete body.county_id;
        }
        if ('name' in core) {
          body.full_name_source = core.name;
          delete body.name;
        }
        await api(`/participants/${id}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      }
      for (const [eid, change] of Object.entries(enr)) {
        if (Object.keys(change).length === 0) continue;
        const { enrollment_no, ...rest } = change;
        await api(`/participants/${id}/enrollments/${eid}`, {
          method: 'PATCH',
          body: JSON.stringify({
            ...rest,
            ...(enrollment_no !== undefined
              ? { source_enrollment_no: enrollment_no }
              : {}),
          }),
        });
      }
    },
    onSuccess: () => {
      toast.success('Participant updated.');
      void qc.invalidateQueries({ queryKey: ['participants'] });
      void qc.invalidateQueries({ queryKey: ['participant', id] });
      onClose();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  const text = (
    key: 'name' | 'given_name' | 'family_name' | 'other_names',
    label: string,
  ) =>
    v && (
      <div className="space-y-1.5">
        <Label htmlFor={`pe-${key}`}>{label}</Label>
        <Input
          id={`pe-${key}`}
          value={v[key]}
          onChange={(e) => setCore((c) => ({ ...c, [key]: e.target.value }))}
        />
      </div>
    );

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && onClose()}
      title="Edit participant"
      description="Only the fields you change are saved, and each change is recorded in the audit log."
      submitLabel="Save changes"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        setError('');
        if (v && !v.name.trim()) return setError('Enter the full name.');
        save.mutate();
      }}
    >
      {detail.isPending && <LoadingState />}
      {detail.isError && (
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      )}
      {v && (
        <div className="max-h-[65vh] space-y-4 overflow-y-auto pe-1">
          {text('name', 'Full name (as shown in lists)')}
          <div className="grid gap-4 sm:grid-cols-3">
            {text('given_name', 'Given name')}
            {text('family_name', 'Family name')}
            {text('other_names', 'Other names')}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Gender</Label>
              <SelectField
                label="Gender"
                value={v.gender}
                options={opts(GENDERS)}
                onChange={(x) => setCore((c) => ({ ...c, gender: x }))}
                className="capitalize"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Status</Label>
              <SelectField
                label="Status"
                value={v.status}
                options={opts(STATUSES)}
                onChange={(x) => setCore((c) => ({ ...c, status: x }))}
                className="capitalize"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pe-dob">Date of birth</Label>
              <Input
                id="pe-dob"
                type="date"
                value={v.date_of_birth ?? ''}
                onChange={(e) =>
                  setCore((c) => ({
                    ...c,
                    date_of_birth: e.target.value || null,
                  }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pe-age">Age (as recorded at source)</Label>
              <Input
                id="pe-age"
                type="number"
                min={0}
                max={120}
                value={v.age_at_source ?? ''}
                onChange={(e) =>
                  setCore((c) => ({
                    ...c,
                    age_at_source: e.target.value
                      ? Number(e.target.value)
                      : null,
                  }))
                }
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label>Home county</Label>
              <SelectField
                label="Home county"
                value={v.county_id || NO_COUNTY}
                options={[
                  { id: NO_COUNTY, name: 'Not recorded' },
                  ...(filters.data?.counties ?? []),
                ]}
                onChange={(x) =>
                  setCore((c) => ({
                    ...c,
                    county_id: x === NO_COUNTY ? '' : x,
                  }))
                }
              />
            </div>
          </div>

          {d!.enrollments.map((e) => {
            const m = { ...e, ...enr[e.id] };
            return (
              <fieldset
                key={e.id}
                className="space-y-3 rounded-lg border border-border p-3"
              >
                <legend className="px-1 text-sm font-medium">
                  {e.programme}: {e.cohort}, {e.course}
                </legend>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor={`en-no-${e.id}`}>Enrollment no.</Label>
                    <Input
                      id={`en-no-${e.id}`}
                      value={m.enrollment_no}
                      onChange={(x) =>
                        patchEnr(e.id, { enrollment_no: x.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Enrollment status</Label>
                    <SelectField
                      label="Enrollment status"
                      value={m.status}
                      options={opts(ENROLLMENT)}
                      onChange={(x) => patchEnr(e.id, { status: x })}
                      className="capitalize"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`en-start-${e.id}`}>Enrolled on</Label>
                    <Input
                      id={`en-start-${e.id}`}
                      type="date"
                      value={m.enrolled_on ?? ''}
                      onChange={(x) =>
                        patchEnr(e.id, { enrolled_on: x.target.value || null })
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`en-end-${e.id}`}>Completed on</Label>
                    <Input
                      id={`en-end-${e.id}`}
                      type="date"
                      value={m.completed_on ?? ''}
                      onChange={(x) =>
                        patchEnr(e.id, { completed_on: x.target.value || null })
                      }
                    />
                  </div>
                  <div className="space-y-1.5 sm:col-span-2">
                    <Label htmlFor={`en-exit-${e.id}`}>Exit reason</Label>
                    <Input
                      id={`en-exit-${e.id}`}
                      value={m.exit_reason}
                      onChange={(x) =>
                        patchEnr(e.id, { exit_reason: x.target.value })
                      }
                    />
                  </div>
                </div>
              </fieldset>
            );
          })}
        </div>
      )}
    </FormModal>
  );
}
