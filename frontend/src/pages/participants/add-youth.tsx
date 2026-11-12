import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';

interface Option {
  id: string;
  name: string;
  programme_id?: string;
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

const opts = (xs: string[]) => xs.map((x) => ({ id: x, name: x }));
const BLANK = {
  name: '',
  gender: 'unknown',
  status: 'active',
  age: '',
  county: '',
  cohort: '',
  offering: '',
  enrollmentNo: '',
  phone: '',
  email: '',
};

/** "Add youth" button and form: one youth at a time (the import is for batches). */
export function AddYouth() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [v, setV] = useState(BLANK);
  const [error, setError] = useState('');
  const [matches, setMatches] = useState<Match[]>([]);
  const set = (k: keyof typeof BLANK, val: string) =>
    setV((p) => ({ ...p, [k]: val }));

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
      })) as Option[];
    },
    enabled: open && !!v.cohort && can('config.view'),
  });

  const create = useMutation({
    mutationFn: () =>
      post<{ id: string }>('/participants', {
        full_name_source: v.name.trim(),
        gender: v.gender,
        status: v.status,
        age_at_source: v.age === '' ? null : Number(v.age),
        origin_county_id: v.county || null,
        cohort_course_id: v.offering || null,
        enrollment_no: v.enrollmentNo.trim(),
        phone: v.phone.trim(),
        email: v.email.trim(),
      }),
    onSuccess: (p) => {
      toast.success('Youth added');
      setOpen(false);
      setV(BLANK);
      void qc.invalidateQueries({ queryKey: ['participants'] });
      navigate(`/youth/${p.id}`);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  const submit = async () => {
    setError('');
    if (!v.name.trim()) return setError('A name is required.');
    if (v.cohort && !v.offering && can('config.view'))
      return setError('Choose a course for the cohort, or clear the cohort.');
    if (!matches.length) {
      try {
        const found = await api<{ matches: Match[] }>(
          `/participants/check-name?name=${encodeURIComponent(v.name.trim())}`,
        );
        if (found.matches.length) return setMatches(found.matches);
      } catch {
        /* the check is a courtesy; saving still validates */
      }
    }
    create.mutate();
  };

  if (!can('participants.edit')) return null;
  return (
    <>
      <Button
        onClick={() => {
          setOpen(true);
          setError('');
          setMatches([]);
        }}
      >
        Add youth
      </Button>
      <FormModal
        open={open}
        onOpenChange={setOpen}
        title="Add youth"
        description="Add one youth by hand. To add many at once, use Import participants."
        submitLabel={matches.length ? 'Add anyway' : 'Add youth'}
        pending={create.isPending}
        error={error}
        onSubmit={() => void submit()}
      >
        <Input
          aria-label="Full name"
          placeholder="Full name"
          value={v.name}
          onChange={(e) => {
            set('name', e.target.value);
            setMatches([]);
          }}
          required
        />
        {matches.length > 0 && (
          <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
            Someone with this name is already in the directory:{' '}
            {matches.map((m) => `${m.name} (${m.status})`).join(', ')}. If this
            is a different person, choose “Add anyway”.
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <SelectField
            label="Gender"
            className="w-36 capitalize"
            value={v.gender}
            options={opts(['female', 'male', 'other', 'unknown'])}
            onChange={(x) => set('gender', x)}
          />
          <SelectField
            label="Status"
            className="w-36 capitalize"
            value={v.status}
            options={opts(['active', 'completed', 'withdrawn', 'unknown'])}
            onChange={(x) => set('status', x)}
          />
          <Input
            aria-label="Age"
            placeholder="Age"
            type="number"
            min={0}
            max={120}
            className="w-24"
            value={v.age}
            onChange={(e) => set('age', e.target.value)}
          />
        </div>
        <SelectField
          label="Home county"
          emptyLabel="Home county (unknown)"
          value={v.county}
          options={filters.data?.counties ?? []}
          onChange={(x) => set('county', x)}
        />
        <div className="space-y-2">
          <p className="text-sm font-medium">Enrollment (optional)</p>
          <div className="flex flex-wrap gap-2">
            <SelectField
              label="Cohort"
              emptyLabel="No cohort yet"
              className="w-56"
              value={v.cohort}
              options={filters.data?.cohorts ?? []}
              onChange={(x) => setV((p) => ({ ...p, cohort: x, offering: '' }))}
            />
            {v.cohort && (
              <SelectField
                label="Course"
                className="w-56"
                value={v.offering}
                options={offerings.data ?? []}
                onChange={(x) => set('offering', x)}
              />
            )}
          </div>
          {v.offering && (
            <Input
              aria-label="Enrollment number"
              placeholder="Enrollment number (optional)"
              value={v.enrollmentNo}
              onChange={(e) => set('enrollmentNo', e.target.value)}
            />
          )}
        </div>
        {can('participants.view_contact') && (
          <div className="flex flex-wrap gap-2">
            <Input
              aria-label="Phone"
              placeholder="Phone"
              className="w-48"
              value={v.phone}
              onChange={(e) => set('phone', e.target.value)}
            />
            <Input
              aria-label="Email"
              placeholder="Email"
              type="email"
              className="w-56"
              value={v.email}
              onChange={(e) => set('email', e.target.value)}
            />
          </div>
        )}
      </FormModal>
    </>
  );
}
