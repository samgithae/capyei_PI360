import { useState } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';
import { ChipPicker, Field } from './cv-fields';
import type {
  Certification,
  Experience,
  LanguageRow,
  Practical,
  ProfileOptions,
  Qualification,
  Readiness,
} from './cv-types';

/** What every record dialog receives: the row being edited (null when adding) and the save. */
export interface DialogProps<T> {
  initial: T | null;
  options: ProfileOptions;
  pending: boolean;
  error: string;
  onSubmit: (row: Record<string, unknown>) => void;
  onClose: () => void;
}

const year = (v: string) => (v.trim() ? Number(v) : null);
const withId = (initial: { id: string | null } | null) =>
  initial?.id ? { id: initial.id } : {};
const shell = (
  title: string,
  p: { pending: boolean; error: string; onClose: () => void },
  submit: () => void,
  body: React.ReactNode,
  localError = '',
) => (
  <FormModal
    open
    onOpenChange={(v) => !v && p.onClose()}
    title={title}
    pending={p.pending}
    error={localError || p.error}
    onSubmit={submit}
  >
    {body}
  </FormModal>
);

export function EducationDialog(p: DialogProps<Qualification>) {
  const i = p.initial;
  const [level, setLevel] = useState(i?.level_id ?? '');
  const [course, setCourse] = useState(i?.title ?? '');
  const [institution, setInstitution] = useState(i?.institution ?? '');
  const [field, setField] = useState(i?.field_of_study ?? '');
  const [grade, setGrade] = useState(i?.grade_id ?? '');
  const [start, setStart] = useState(i?.start_year?.toString() ?? '');
  const [done, setDone] = useState(i?.year_awarded?.toString() ?? '');
  const [studying, setStudying] = useState(i?.currently_studying ?? false);
  const [local, setLocal] = useState('');
  const grades = p.options.grades
    .filter((g) => g.level_id === level)
    .sort((a, b) => b.rank - a.rank);
  return shell(
    i ? 'Edit education' : 'Add education',
    p,
    () => {
      if (!level) return setLocal('Choose the level of education.');
      setLocal('');
      p.onSubmit({
        ...withId(i),
        level_id: level,
        title: course,
        institution,
        field_of_study: field,
        grade_id: grade || null,
        start_year: year(start),
        year_awarded: studying ? null : year(done),
        currently_studying: studying,
      });
    },
    <>
      <Field label="Level of education">
        {() => (
          <SelectField
            label="Level of education"
            className="w-full"
            value={level}
            options={p.options.levels}
            onChange={(v) => {
              setLevel(v);
              setGrade('');
            }}
          />
        )}
      </Field>
      <Field label="Course or qualification">
        {(id) => (
          <Input
            id={id}
            value={course}
            onChange={(e) => setCourse(e.target.value)}
          />
        )}
      </Field>
      <Field label="Institution">
        {(id) => (
          <Input
            id={id}
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
          />
        )}
      </Field>
      <Field label="Field of study" hint="Optional">
        {(id) => (
          <Input
            id={id}
            value={field}
            onChange={(e) => setField(e.target.value)}
          />
        )}
      </Field>
      {grades.length > 0 && (
        <Field label="Grade" hint="Optional">
          {() => (
            <SelectField
              label="Grade"
              className="w-full"
              value={grade}
              options={grades}
              emptyLabel="No grade recorded"
              onChange={setGrade}
            />
          )}
        </Field>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Start year">
          {(id) => (
            <Input
              id={id}
              inputMode="numeric"
              placeholder="2021"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          )}
        </Field>
        <Field label="Completion year">
          {(id) => (
            <Input
              id={id}
              inputMode="numeric"
              placeholder="2024"
              disabled={studying}
              value={studying ? '' : done}
              onChange={(e) => setDone(e.target.value)}
            />
          )}
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={studying}
          onCheckedChange={(v) => setStudying(v === true)}
        />
        I am currently studying here
      </label>
    </>,
    local,
  );
}

export function ExperienceDialog(p: DialogProps<Experience>) {
  const i = p.initial;
  const [title, setTitle] = useState(i?.role_title ?? '');
  const [employer, setEmployer] = useState(i?.employer_name ?? '');
  const [type, setType] = useState(i?.employment_type ?? '');
  const [start, setStart] = useState(i?.start_date ?? '');
  const [end, setEnd] = useState(i?.end_date ?? '');
  const [current, setCurrent] = useState(i?.is_current ?? false);
  const [duties, setDuties] = useState(i?.responsibilities ?? '');
  const [wins, setWins] = useState(i?.achievements ?? '');
  // An older entry with only a number of months keeps it until dates are given.
  const [months, setMonths] = useState(
    i && !i.start_date ? String(i.months) : '',
  );
  const [local, setLocal] = useState('');
  return shell(
    i ? 'Edit work experience' : 'Add work experience',
    p,
    () => {
      if (!title.trim()) return setLocal('Give the job title.');
      if (!start && !months.trim())
        return setLocal('Give the start date, or how many months you worked.');
      setLocal('');
      p.onSubmit({
        ...withId(i),
        role_title: title,
        employer_name: employer,
        employment_type: type,
        start_date: start || null,
        end_date: current ? null : end || null,
        is_current: current,
        responsibilities: duties,
        achievements: wins,
        ...(start ? {} : { months: Number(months || 0) }),
      });
    },
    <>
      <Field label="Job title">
        {(id) => (
          <Input
            id={id}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        )}
      </Field>
      <Field label="Employer">
        {(id) => (
          <Input
            id={id}
            value={employer}
            onChange={(e) => setEmployer(e.target.value)}
          />
        )}
      </Field>
      <Field label="Employment type" hint="Optional">
        {() => (
          <SelectField
            label="Employment type"
            className="w-full"
            value={type}
            options={p.options.employment_types}
            emptyLabel="Not stated"
            onChange={setType}
          />
        )}
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Start date">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          )}
        </Field>
        <Field label="End date">
          {(id) => (
            <Input
              id={id}
              type="date"
              disabled={current}
              value={current ? '' : end}
              onChange={(e) => setEnd(e.target.value)}
            />
          )}
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={current}
          onCheckedChange={(v) => setCurrent(v === true)}
        />
        I currently work here
      </label>
      {!start && (
        <Field label="Months worked" hint="Only if you do not know the dates">
          {(id) => (
            <Input
              id={id}
              inputMode="numeric"
              value={months}
              onChange={(e) => setMonths(e.target.value)}
            />
          )}
        </Field>
      )}
      <Field label="Responsibilities" hint="One point per line">
        {(id) => (
          <Textarea
            id={id}
            rows={4}
            maxLength={3000}
            value={duties}
            onChange={(e) => setDuties(e.target.value)}
          />
        )}
      </Field>
      <Field label="Achievements" hint="Optional. One point per line">
        {(id) => (
          <Textarea
            id={id}
            rows={3}
            maxLength={3000}
            value={wins}
            onChange={(e) => setWins(e.target.value)}
          />
        )}
      </Field>
    </>,
    local,
  );
}

export function PracticalDialog(p: DialogProps<Practical>) {
  const i = p.initial;
  const [org, setOrg] = useState(i?.organisation ?? '');
  const [role, setRole] = useState(i?.role ?? '');
  const [kind, setKind] = useState(i?.kind ?? '');
  const [start, setStart] = useState(i?.start_date ?? '');
  const [end, setEnd] = useState(i?.end_date ?? '');
  const [text, setText] = useState(i?.description ?? '');
  const [local, setLocal] = useState('');
  return shell(
    i ? 'Edit practical experience' : 'Add practical experience',
    p,
    () => {
      if (!org.trim()) return setLocal('Give the organisation.');
      if (!kind) return setLocal('Choose the type.');
      setLocal('');
      p.onSubmit({
        ...withId(i),
        organisation: org,
        role,
        kind,
        start_date: start || null,
        end_date: end || null,
        description: text,
      });
    },
    <>
      <Field label="Type">
        {() => (
          <SelectField
            label="Type"
            className="w-full"
            value={kind}
            options={p.options.practical_kinds}
            onChange={setKind}
          />
        )}
      </Field>
      <Field label="Organisation">
        {(id) => (
          <Input id={id} value={org} onChange={(e) => setOrg(e.target.value)} />
        )}
      </Field>
      <Field label="Role" hint="Optional">
        {(id) => (
          <Input
            id={id}
            value={role}
            onChange={(e) => setRole(e.target.value)}
          />
        )}
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Start date">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          )}
        </Field>
        <Field label="End date">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          )}
        </Field>
      </div>
      <Field label="What you did" hint="One point per line">
        {(id) => (
          <Textarea
            id={id}
            rows={4}
            maxLength={3000}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        )}
      </Field>
    </>,
    local,
  );
}

export function CertificationDialog(p: DialogProps<Certification>) {
  const i = p.initial;
  const [name, setName] = useState(i?.name ?? '');
  const [issuer, setIssuer] = useState(i?.issuer ?? '');
  const [yr, setYr] = useState(i?.year_obtained?.toString() ?? '');
  const [expiry, setExpiry] = useState(i?.expiry_date ?? '');
  const [local, setLocal] = useState('');
  return shell(
    i ? 'Edit certification' : 'Add certification or training',
    p,
    () => {
      if (!name.trim()) return setLocal('Give the name of the certificate.');
      setLocal('');
      p.onSubmit({
        ...withId(i),
        name,
        issuer,
        year_obtained: year(yr),
        expiry_date: expiry || null,
      });
    },
    <>
      <Field label="Certificate or training name">
        {(id) => (
          <Input
            id={id}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        )}
      </Field>
      <Field label="Issuing organisation">
        {(id) => (
          <Input
            id={id}
            value={issuer}
            onChange={(e) => setIssuer(e.target.value)}
          />
        )}
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Year obtained">
          {(id) => (
            <Input
              id={id}
              inputMode="numeric"
              value={yr}
              onChange={(e) => setYr(e.target.value)}
            />
          )}
        </Field>
        <Field label="Expiry date" hint="Optional">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
            />
          )}
        </Field>
      </div>
    </>,
    local,
  );
}

export function LanguageDialog(p: DialogProps<LanguageRow>) {
  const i = p.initial;
  const [language, setLanguage] = useState(i?.language ?? '');
  const [level, setLevel] = useState(i?.proficiency ?? 'fluent');
  const [local, setLocal] = useState('');
  const listId = 'cv-language-suggestions';
  return shell(
    i ? 'Edit language' : 'Add language',
    p,
    () => {
      if (!language.trim()) return setLocal('Give the language.');
      setLocal('');
      p.onSubmit({
        ...withId(i),
        language: language.trim(),
        proficiency: level,
      });
    },
    <>
      <Field label="Language" hint="Pick a suggestion or type your own">
        {(id) => (
          <>
            <Input
              id={id}
              list={listId}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            />
            <datalist id={listId}>
              {p.options.languages.map((l) => (
                <option key={l} value={l} />
              ))}
            </datalist>
          </>
        )}
      </Field>
      <Field label="Proficiency">
        {() => (
          <SelectField
            label="Proficiency"
            className="w-full"
            value={level}
            options={p.options.language_levels}
            onChange={setLevel}
          />
        )}
      </Field>
    </>,
    local,
  );
}

const TRI = [
  { id: 'yes', name: 'Yes' },
  { id: 'no', name: 'No' },
];

/** Summary and employment preferences: the parts of the CV that are not a list of records. */
export function AboutDialog({
  readiness: r,
  options: o,
  pending,
  error,
  onSubmit,
  onClose,
}: {
  readiness: Readiness;
  options: ProfileOptions;
  pending: boolean;
  error: string;
  onSubmit: (readiness: Record<string, unknown>) => void;
  onClose: () => void;
}) {
  const [summary, setSummary] = useState(r.summary);
  const [roles, setRoles] = useState(r.preferred_roles.join(', '));
  const [sectors, setSectors] = useState(r.interest_sector_ids);
  const [counties, setCounties] = useState(r.preferred_county_ids);
  const [patterns, setPatterns] = useState(r.work_patterns);
  const [from, setFrom] = useState(r.available_from ?? '');
  const [relocate, setRelocate] = useState(
    r.willing_to_relocate === null ? '' : r.willing_to_relocate ? 'yes' : 'no',
  );
  const toggle = (c: string) =>
    setPatterns(
      patterns.includes(c) ? patterns.filter((x) => x !== c) : [...patterns, c],
    );
  return (
    <FormModal
      open
      onOpenChange={(v) => !v && onClose()}
      title="Summary and preferences"
      description="Two to four sentences about you, and the kind of work you want."
      pending={pending}
      error={error}
      onSubmit={() =>
        onSubmit({
          summary,
          preferred_roles: roles
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean),
          interest_sector_ids: sectors,
          preferred_county_ids: counties,
          work_patterns: patterns,
          available_from: from || null,
          willing_to_relocate: relocate ? relocate === 'yes' : null,
        })
      }
    >
      <Field
        label="Professional summary"
        hint={`${summary.length} of 600 characters`}
      >
        {(id) => (
          <Textarea
            id={id}
            rows={5}
            maxLength={600}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
          />
        )}
      </Field>
      <Field label="Preferred roles" hint="Separate with commas. Up to 15.">
        {(id) => (
          <Input
            id={id}
            value={roles}
            onChange={(e) => setRoles(e.target.value)}
          />
        )}
      </Field>
      <Field label="Preferred sectors">
        {() => (
          <ChipPicker
            label="Add a sector"
            options={o.sectors}
            value={sectors}
            onChange={setSectors}
          />
        )}
      </Field>
      <Field label="Preferred counties">
        {() => (
          <ChipPicker
            label="Add a county"
            options={o.counties}
            value={counties}
            onChange={setCounties}
          />
        )}
      </Field>
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">Work pattern</legend>
        <div className="flex flex-wrap gap-4 text-sm">
          {o.work_patterns.map((w) => (
            <label key={w.id} className="flex items-center gap-2">
              <Checkbox
                checked={patterns.includes(w.id)}
                onCheckedChange={() => toggle(w.id)}
              />
              {w.name}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Available from">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          )}
        </Field>
        <Field label="Willing to relocate">
          {() => (
            <SelectField
              label="Willing to relocate"
              className="w-full"
              value={relocate}
              options={TRI}
              emptyLabel="Not stated"
              onChange={setRelocate}
            />
          )}
        </Field>
      </div>
    </FormModal>
  );
}
