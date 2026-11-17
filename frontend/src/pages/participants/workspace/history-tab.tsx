import { useAuth } from '@/auth/auth-context';
import { Link } from 'react-router';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataCard } from '@/components/data-card';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { Fact } from '../cv/cv-types';
import { useProfile } from './queries';
import { entryStatus } from './readiness';
import { monthsText, shortDate, type Detail } from './types';

function Check({ f }: { f: Fact }) {
  const s = entryStatus(f);
  if (s === 'verified')
    return (
      <Badge variant="success" appearance="light" size="sm">
        Verified
      </Badge>
    );
  if (s === 'needs_reassessment')
    return (
      <Badge variant="warning" appearance="light" size="sm">
        Needs reassessment
      </Badge>
    );
  if (s === 'rejected')
    return (
      <Badge variant="destructive" appearance="light" size="sm">
        Rejected
      </Badge>
    );
  return (
    <Badge variant="secondary" appearance="light" size="sm">
      {f.source === 'youth' ? 'Self-reported' : 'Not verified'}
    </Badge>
  );
}

function Item({
  title,
  lines,
  fact,
}: {
  title: string;
  lines: (string | null | undefined)[];
  fact?: Fact;
}) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-2 p-4">
      <div className="min-w-0">
        <p className="font-medium break-words">{title}</p>
        {lines.filter(Boolean).map((l, i) => (
          <p key={i} className="text-sm break-words text-muted-foreground">
            {l}
          </p>
        ))}
      </div>
      {fact && <Check f={fact} />}
    </li>
  );
}

const range = (a?: string | null, b?: string | null, current?: boolean) =>
  [shortDate(a), current ? 'present' : shortDate(b)]
    .filter(Boolean)
    .join(' to ');

/** Education, work and practical experience, newest first, with how each entry was checked. */
export function HistoryTab({ p }: { p: Detail }) {
  const { can } = useAuth();
  const q = useProfile(p.id);
  if (!can('participants.view_profile'))
    return (
      <EmptyState
        title="Not available for your role"
        hint="Your role cannot view skills and readiness."
      />
    );
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const d = q.data;
  const work = d.experience
    .slice()
    .sort((a, b) => (b.start_date ?? '').localeCompare(a.start_date ?? ''));
  const empty =
    !d.qualifications.length &&
    !d.experience.length &&
    !d.practical.length &&
    !d.certifications.length &&
    !p.enrollments.length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          To change these entries, use the CV Profile tab.
        </p>
        {can('participants.edit') && (
          <Button asChild size="sm" variant="outline">
            <Link to="?tab=cv">Edit on CV Profile</Link>
          </Button>
        )}
      </div>
      {empty && (
        <EmptyState
          title="No education or experience recorded"
          hint="Add them on the CV Profile tab. If the youth has no work experience yet, tick that there; it does not lower the CV completeness."
        />
      )}
      {(d.qualifications.length > 0 || p.enrollments.length > 0) && (
        <DataCard title="Education and training">
          <ul className="divide-y divide-border">
            {d.qualifications.map((x) => (
              <Item
                key={x.id}
                fact={x}
                title={x.title || x.level}
                lines={[
                  [x.level, x.institution].filter(Boolean).join(', '),
                  [x.field_of_study, x.grade].filter(Boolean).join(', '),
                  x.currently_studying
                    ? `${x.start_year ?? ''} to present`.trim()
                    : [x.start_year, x.year_awarded]
                        .filter(Boolean)
                        .join(' to '),
                ]}
              />
            ))}
            {p.enrollments
              .filter((e) => e.course || e.institution)
              .map((e) => (
                <Item
                  key={e.id}
                  title={e.course || e.programme}
                  lines={[
                    [e.institution, e.programme].filter(Boolean).join(', '),
                    range(e.enrolled_on, e.completed_on),
                    'Programme enrolment',
                  ]}
                />
              ))}
          </ul>
        </DataCard>
      )}
      {work.length > 0 && (
        <DataCard title="Work experience">
          <ul className="divide-y divide-border">
            {work.map((x) => (
              <Item
                key={x.id}
                fact={x}
                title={x.role_title}
                lines={[
                  [x.employer_name, x.sector].filter(Boolean).join(', '),
                  [
                    range(x.start_date, x.end_date, x.is_current),
                    monthsText(x.months),
                  ]
                    .filter(Boolean)
                    .join(' · '),
                  x.responsibilities,
                  x.achievements ? `Achievements: ${x.achievements}` : '',
                ]}
              />
            ))}
          </ul>
        </DataCard>
      )}
      {d.practical.length > 0 && (
        <DataCard title="Internships, attachments and volunteering">
          <ul className="divide-y divide-border">
            {d.practical.map((x) => (
              <Item
                key={x.id}
                fact={x}
                title={x.role || x.organisation}
                lines={[
                  [x.organisation, x.kind].filter(Boolean).join(', '),
                  range(x.start_date, x.end_date),
                  x.description,
                ]}
              />
            ))}
          </ul>
        </DataCard>
      )}
      {d.certifications.length > 0 && (
        <DataCard title="Certifications">
          <ul className="divide-y divide-border">
            {d.certifications.map((x) => (
              <Item
                key={x.id}
                fact={x}
                title={x.name}
                lines={[
                  x.issuer,
                  [
                    x.year_obtained,
                    x.expiry_date ? `expires ${shortDate(x.expiry_date)}` : '',
                  ]
                    .filter(Boolean)
                    .join(' · '),
                ]}
              />
            ))}
          </ul>
        </DataCard>
      )}
    </div>
  );
}
