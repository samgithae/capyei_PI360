import { useRef, useState, type ReactNode } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Pencil, Plus, Trash2, UserRound, X } from 'lucide-react';
import { api, ApiError, apiUrl, del, upload } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { DataCard } from '@/components/data-card';
import { ConfirmDialog } from '@/components/shared/modals';
import {
  SKILL_LEVELS,
  SkillPickerDialog,
} from '@/components/shared/skill-picker';
import {
  AboutDialog,
  CertificationDialog,
  EducationDialog,
  ExperienceDialog,
  LanguageDialog,
  PracticalDialog,
  type DialogProps,
} from './cv-dialogs';
import type {
  CvDoc,
  CvPaths,
  CvProfileData,
  Fact,
  ProfileOptions,
  Section,
} from './cv-types';

const message = (e: unknown) =>
  e instanceof ApiError ? e.message : 'Could not save. Try again.';
const join = (...p: (string | number | null | undefined)[]) =>
  p.filter(Boolean).join(' | ');

/** One mutation shared by the editor: PUT part of the profile, then tell the page to reload. */
function useProfileSave(paths: CvPaths, onChanged: () => void) {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api(paths.save, { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: onChanged,
  });
}
type Save = ReturnType<typeof useProfileSave>;

/**
 * A list of records with Add, Edit and Remove. A save sends the whole list for this section, so
 * the section is replaced as one unit; rows that were not touched are sent back unchanged.
 */
function Repeatable<T extends Fact>({
  title,
  addLabel,
  section,
  items,
  describe,
  save,
  Dialog,
  options,
  confirmText,
  footer,
}: {
  title: string;
  addLabel: string;
  section: Section;
  items: T[];
  describe: (x: T) => { title: string; when?: string; lines?: string[] };
  save: Save;
  Dialog: (p: DialogProps<T>) => ReactNode;
  options: ProfileOptions;
  confirmText: string;
  footer?: ReactNode;
}) {
  const [editing, setEditing] = useState<T | 'new' | null>(null);
  const [removing, setRemoving] = useState<T | null>(null);

  const send = (list: unknown[], done?: () => void) =>
    save.mutate({ [section]: list }, { onSuccess: done });
  // Rows go back as read; the server ignores read-only keys such as "verified".
  const rows = (skip?: string | null) =>
    items.filter((x) => x.id !== skip).map((x) => ({ ...x }));

  return (
    <DataCard
      title={title}
      toolbar={
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            save.reset();
            setEditing('new');
          }}
        >
          <Plus /> {addLabel}
        </Button>
      }
    >
      <div className="space-y-3 p-5 text-sm">
        {items.length === 0 && (
          <p className="text-muted-foreground">Nothing added yet.</p>
        )}
        <ul className="divide-y divide-border">
          {items.map((x) => {
            const d = describe(x);
            return (
              <li
                key={x.id}
                className="flex items-start justify-between gap-3 py-2 first:pt-0"
              >
                <div className="min-w-0">
                  <p className="font-medium">{d.title}</p>
                  {d.when && (
                    <p className="text-xs text-muted-foreground">{d.when}</p>
                  )}
                  {d.lines?.filter(Boolean).map((l) => (
                    <p key={l} className="text-muted-foreground">
                      {l}
                    </p>
                  ))}
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Edit ${d.title}`}
                    onClick={() => {
                      save.reset();
                      setEditing(x);
                    }}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Remove ${d.title}`}
                    onClick={() => {
                      save.reset();
                      setRemoving(x);
                    }}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
        {footer}
        {save.isError && !editing && (
          <p role="alert" className="text-destructive">
            {message(save.error)}
          </p>
        )}
      </div>
      {editing && (
        <Dialog
          initial={editing === 'new' ? null : editing}
          options={options}
          pending={save.isPending}
          error={save.isError ? message(save.error) : ''}
          onClose={() => setEditing(null)}
          onSubmit={(row) => {
            const list =
              editing === 'new'
                ? [...rows(), row]
                : items.map((x) => (x.id === editing.id ? row : { ...x }));
            send(list, () => setEditing(null));
          }}
        />
      )}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(v) => !v && setRemoving(null)}
        title={`Remove from ${title.toLowerCase()}?`}
        description={confirmText}
        onConfirm={() => {
          const id = removing?.id;
          setRemoving(null);
          send(rows(id));
        }}
      />
    </DataCard>
  );
}

function Photo({
  paths,
  has,
  version,
  onChanged,
}: {
  paths: CvPaths;
  has: boolean;
  version: number;
  onChanged: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState('');
  const send = useMutation({
    mutationFn: (file: File) => upload(paths.photo, { photo: file }),
    onSuccess: onChanged,
    onError: (e) => setError(message(e)),
  });
  const remove = useMutation({
    mutationFn: () => del(paths.photo),
    onSuccess: onChanged,
    onError: (e) => setError(message(e)),
  });
  return (
    <div className="flex items-center gap-4 p-5">
      {has ? (
        <img
          src={`${apiUrl(paths.photo)}?v=${version}`}
          alt="Your photo"
          className="size-20 rounded-md border border-border object-cover"
        />
      ) : (
        <div className="flex size-20 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <UserRound className="size-8" />
        </div>
      )}
      <div className="space-y-1 text-sm">
        <p className="text-muted-foreground">
          Optional. A clear head-and-shoulders photo in JPG, PNG or WebP, up to
          5 MB. It is cropped to a square.
        </p>
        <input
          ref={input}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          aria-label="Choose a photo"
          className="sr-only"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (!file) return;
            setError('');
            if (file.size > 5 * 1024 * 1024)
              return setError('That photo is over 5 MB.');
            send.mutate(file);
          }}
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={send.isPending}
            onClick={() => input.current?.click()}
          >
            {send.isPending
              ? 'Uploading...'
              : has
                ? 'Change photo'
                : 'Add photo'}
          </Button>
          {has && (
            <Button
              size="sm"
              variant="ghost"
              disabled={remove.isPending}
              onClick={() => {
                setError('');
                remove.mutate();
              }}
            >
              <X /> Remove
            </Button>
          )}
        </div>
        {error && (
          <p role="alert" className="text-destructive">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

export function SkillsCard({
  profile,
  save,
  endpoint,
}: {
  profile: CvProfileData;
  save: Save;
  endpoint: string;
}) {
  const [picking, setPicking] = useState(false);
  const rows = (change: (s: CvProfileData['skills']) => unknown[]) =>
    save.mutate({ skills: change(profile.skills) });
  return (
    <DataCard title="Skills and competencies">
      <div className="space-y-3 p-5 text-sm">
        {profile.skills.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {profile.skills.map((s) => (
              <li
                key={s.skill_id}
                className="flex items-center gap-1 rounded-full bg-primary/10 py-0.5 ps-3 pe-1 text-primary"
              >
                <span className="font-medium">{s.skill}</span>
                <select
                  aria-label={`Level of ${s.skill}`}
                  className="rounded bg-transparent text-xs"
                  value={String(s.proficiency)}
                  onChange={(e) =>
                    rows((all) =>
                      all.map((x) =>
                        x.skill_id === s.skill_id
                          ? { ...x, proficiency: Number(e.target.value) }
                          : { ...x },
                      ),
                    )
                  }
                >
                  {SKILL_LEVELS.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  aria-label={`Remove ${s.skill}`}
                  className="rounded-full p-1 hover:text-destructive"
                  onClick={() =>
                    rows((all) =>
                      all
                        .filter((x) => x.skill_id !== s.skill_id)
                        .map((x) => ({ ...x })),
                    )
                  }
                >
                  <X className="size-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
        <Button
          type="button"
          variant="outline"
          onClick={() => setPicking(true)}
        >
          <Plus /> Choose skills
        </Button>
        {save.isError && !picking && (
          <p role="alert" className="text-destructive">
            {message(save.error)}
          </p>
        )}
      </div>
      <SkillPickerDialog
        open={picking}
        onOpenChange={setPicking}
        endpoint={endpoint}
        mode="level"
        title="Choose skills"
        description="Search for a skill, or pick from the popular ones and the categories. Pick as many as you like, then set how well you know each one."
        saveLabel="Save skills"
        resetKey={profile.skills.map((s) => s.skill_id).join(',')}
        initial={profile.skills.map((s) => ({
          id: s.skill_id,
          name: s.skill,
          level: s.proficiency,
        }))}
        canAdd
        saving={save.isPending}
        error={save.isError ? message(save.error) : ''}
        onSave={(picked) => {
          // Keep the row id of a skill already on the profile: the server
          // matches rows by id, and a row without one is a new insert (which
          // the one-skill-per-youth rule refuses).
          const held = new Map(profile.skills.map((s) => [s.skill_id, s.id]));
          save.mutate(
            {
              skills: picked.map((p) => ({
                id: held.get(p.id),
                skill_id: p.id,
                proficiency: p.level ?? 2,
              })),
            },
            { onSuccess: () => setPicking(false) },
          );
        }}
      />
    </DataCard>
  );
}

/** Everything a youth edits to build the CV, one card per section. */
export function CvEditor({
  paths,
  profile,
  cv,
  photoVersion,
  onChanged,
}: {
  paths: CvPaths;
  profile: CvProfileData;
  cv: CvDoc | undefined;
  photoVersion: number;
  onChanged: () => void;
}) {
  const save = useProfileSave(paths, onChanged);
  const [about, setAbout] = useState(false);
  const o = profile.options;
  const r = profile.readiness;
  const opt = (list: { id: string; name: string }[], id: string) =>
    list.find((x) => x.id === id)?.name ?? id;

  return (
    <div className="space-y-5">
      <DataCard title="Photo">
        <Photo
          paths={paths}
          has={!!cv?.has_photo}
          version={photoVersion}
          onChanged={onChanged}
        />
      </DataCard>

      <DataCard
        title="Summary and preferences"
        toolbar={
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              save.reset();
              setAbout(true);
            }}
          >
            <Pencil /> Edit
          </Button>
        }
      >
        <div className="space-y-1 p-5 text-sm">
          {r.summary ? (
            <p className="whitespace-pre-line">{r.summary}</p>
          ) : (
            <p className="text-muted-foreground">
              Write two to four sentences about you and the work you want.
            </p>
          )}
          {r.preferred_roles.length > 0 && (
            <p>
              <span className="text-muted-foreground">Preferred roles: </span>
              {r.preferred_roles.join(', ')}
            </p>
          )}
          {r.interest_sectors.length > 0 && (
            <p>
              <span className="text-muted-foreground">Sectors: </span>
              {r.interest_sectors.join(', ')}
            </p>
          )}
          {r.preferred_counties.length > 0 && (
            <p>
              <span className="text-muted-foreground">Locations: </span>
              {r.preferred_counties.join(', ')}
            </p>
          )}
        </div>
      </DataCard>
      {about && (
        <AboutDialog
          readiness={r}
          options={o}
          pending={save.isPending}
          error={save.isError ? message(save.error) : ''}
          onClose={() => setAbout(false)}
          onSubmit={(readiness) =>
            save.mutate({ readiness }, { onSuccess: () => setAbout(false) })
          }
        />
      )}

      <Repeatable
        title="Education"
        addLabel="Add education"
        section="qualifications"
        items={profile.qualifications}
        save={save}
        confirmText="This education record will be removed from your CV."
        describe={(q) => ({
          title: q.title || q.level,
          when: q.currently_studying
            ? `${q.start_year ?? ''} - Present`
            : [q.start_year, q.year_awarded].filter(Boolean).join(' - '),
          lines: [join(q.institution, q.title ? q.level : '', q.grade)],
        })}
        Dialog={EducationDialog}
        options={o}
      />

      <Repeatable
        title="Work experience"
        addLabel="Add work experience"
        section="experience"
        items={profile.experience}
        save={save}
        confirmText="This job will be removed from your CV."
        describe={(e) => ({
          title: e.role_title,
          when: e.start_date
            ? `${e.start_date} - ${e.is_current ? 'Present' : (e.end_date ?? '')}`
            : `${e.months} months`,
          lines: [
            join(
              e.employer_name,
              e.employment_type
                ? opt(o.employment_types, e.employment_type)
                : '',
            ),
          ],
        })}
        Dialog={ExperienceDialog}
        options={o}
        footer={
          profile.experience.length === 0 && (
            <label className="flex items-center gap-2">
              <Checkbox
                checked={r.no_work_experience}
                disabled={save.isPending}
                onCheckedChange={(v) =>
                  save.mutate({ readiness: { no_work_experience: v === true } })
                }
              />
              I have no formal work experience yet
            </label>
          )
        }
      />

      <Repeatable
        title="Internships and practical experience"
        addLabel="Add practical experience"
        section="practical"
        items={profile.practical}
        save={save}
        confirmText="This entry will be removed from your CV."
        describe={(x) => ({
          title: x.role || opt(o.practical_kinds, x.kind),
          when: [x.start_date, x.end_date].filter(Boolean).join(' - '),
          lines: [
            join(x.organisation, x.role ? opt(o.practical_kinds, x.kind) : ''),
          ],
        })}
        Dialog={PracticalDialog}
        options={o}
      />

      <SkillsCard profile={profile} save={save} endpoint={paths.skills} />

      <Repeatable
        title="Certifications and training"
        addLabel="Add certification"
        section="certifications"
        items={profile.certifications}
        save={save}
        confirmText="This certification will be removed from your CV."
        describe={(c) => ({
          title: c.name,
          when: c.year_obtained ? String(c.year_obtained) : '',
          lines: [
            join(c.issuer, c.expiry_date ? `Expires ${c.expiry_date}` : ''),
          ],
        })}
        Dialog={CertificationDialog}
        options={o}
      />

      <Repeatable
        title="Languages"
        addLabel="Add language"
        section="languages"
        items={profile.languages}
        save={save}
        confirmText="This language will be removed from your CV."
        describe={(l) => ({
          title: l.language,
          lines: [opt(o.language_levels, l.proficiency)],
        })}
        Dialog={LanguageDialog}
        options={o}
      />
    </div>
  );
}
