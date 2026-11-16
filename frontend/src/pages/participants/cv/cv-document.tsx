import { type ReactNode } from 'react';
import { Mail, MapPin, Phone, UserRound } from 'lucide-react';
import type { CvDoc } from './cv-types';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="border-b border-border pb-1 text-xs font-semibold tracking-wide text-primary uppercase">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Entry({
  title,
  when,
  lines,
  bullets,
}: {
  title: string;
  when?: string;
  lines?: string[];
  bullets?: string[];
}) {
  return (
    <div className="space-y-0.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <p className="font-semibold">{title}</p>
        {when && <p className="text-xs text-muted-foreground">{when}</p>}
      </div>
      {lines?.filter(Boolean).map((l) => (
        <p key={l} className="text-muted-foreground">
          {l}
        </p>
      ))}
      {bullets && bullets.length > 0 && (
        <ul className="list-disc space-y-0.5 ps-5">
          {bullets.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

const lines = (text: string) =>
  text
    .split('\n')
    .map((x) => x.replace(/^[\s•-]+/, '').trim())
    .filter(Boolean);
const join = (...parts: (string | undefined | null)[]) =>
  parts.filter(Boolean).join(' | ');

/** The CV as an employer reads it. Drawn from the same document as the PDF, so they match. */
export function CvDocument({
  cv,
  photoUrl,
}: {
  cv: CvDoc;
  photoUrl?: string | null;
}) {
  const c = cv.contact;
  const pref = cv.preferences;
  return (
    <article
      aria-label={`${cv.name} curriculum vitae`}
      className="mx-auto max-w-3xl space-y-5 rounded-lg border border-border bg-card p-5 text-sm shadow-xs sm:p-8"
    >
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h2 className="text-2xl font-bold break-words text-primary">
            {cv.name}
          </h2>
          {cv.headline && (
            <p className="text-base text-muted-foreground">{cv.headline}</p>
          )}
          <ul className="space-y-0.5 pt-1">
            {c.phone && (
              <li className="flex items-center gap-2">
                <Phone className="size-3.5 text-muted-foreground" /> {c.phone}
              </li>
            )}
            {c.email && (
              <li className="flex items-center gap-2 break-all">
                <Mail className="size-3.5 text-muted-foreground" /> {c.email}
              </li>
            )}
            {c.location && (
              <li className="flex items-center gap-2">
                <MapPin className="size-3.5 text-muted-foreground" />{' '}
                {c.location}
              </li>
            )}
          </ul>
        </div>
        {cv.has_photo && photoUrl ? (
          <img
            src={photoUrl}
            alt={`Photo of ${cv.name}`}
            className="size-24 shrink-0 rounded-md border border-border object-cover"
          />
        ) : (
          <div
            aria-hidden
            className="hidden size-24 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground sm:flex"
          >
            <UserRound className="size-10" />
          </div>
        )}
      </header>

      {cv.summary && (
        <Section title="Professional summary">
          <p className="whitespace-pre-line">{cv.summary}</p>
        </Section>
      )}

      {(cv.experience.length > 0 || cv.no_work_experience) && (
        <Section title="Work experience">
          {cv.experience.length === 0 && (
            <p className="text-muted-foreground">
              No formal work experience yet.
            </p>
          )}
          {cv.experience.map((e, i) => (
            <Entry
              key={i}
              title={e.title}
              when={join(e.period, e.duration)}
              lines={[join(e.employer, e.employment_type)]}
              bullets={[
                ...lines(e.responsibilities),
                ...lines(e.achievements).map((a) => `Achievement: ${a}`),
              ]}
            />
          ))}
        </Section>
      )}

      {cv.practical.length > 0 && (
        <Section title="Internships and practical experience">
          {cv.practical.map((x, i) => (
            <Entry
              key={i}
              title={x.role || x.kind}
              when={x.period}
              lines={[join(x.organisation, x.role ? x.kind : '')]}
              bullets={lines(x.description)}
            />
          ))}
        </Section>
      )}

      {cv.education.length > 0 && (
        <Section title="Education">
          {cv.education.map((q, i) => (
            <Entry
              key={i}
              title={q.course || q.level}
              when={q.period}
              lines={[
                join(q.institution, q.course ? q.level : ''),
                join(q.field_of_study, q.grade ? `Grade: ${q.grade}` : ''),
              ]}
            />
          ))}
        </Section>
      )}

      {cv.skills.length > 0 && (
        <Section title="Skills">
          <ul className="flex flex-wrap gap-1.5">
            {cv.skills.map((s) => (
              <li
                key={s.name}
                className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary"
              >
                {s.name}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {cv.certifications.length > 0 && (
        <Section title="Certifications and training">
          {cv.certifications.map((c2, i) => (
            <Entry
              key={i}
              title={c2.name}
              when={c2.year ? String(c2.year) : ''}
              lines={[join(c2.issuer, c2.expiry ? `Expires ${c2.expiry}` : '')]}
            />
          ))}
        </Section>
      )}

      {cv.languages.length > 0 && (
        <Section title="Languages">
          <p>
            {cv.languages
              .map((l) => (l.level ? `${l.language} (${l.level})` : l.language))
              .join('  |  ')}
          </p>
        </Section>
      )}

      {pref && (
        <Section title="Employment preferences">
          <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[10rem_1fr]">
            {[
              ['Preferred roles', pref.roles.join(', ')],
              ['Sectors', pref.sectors.join(', ')],
              ['Preferred locations', pref.counties.join(', ')],
              ['Work pattern', pref.work_patterns.join(', ')],
              ['Available from', pref.available_from],
              [
                'Willing to relocate',
                pref.willing_to_relocate === null
                  ? ''
                  : pref.willing_to_relocate
                    ? 'Yes'
                    : 'No',
              ],
            ]
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
          </dl>
        </Section>
      )}
    </article>
  );
}
