import { useAuth } from '@/auth/auth-context';
import { CheckCircle2, Circle } from 'lucide-react';
import { Link } from 'react-router';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataCard } from '@/components/data-card';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { ActivityFeed } from './activity';
import { useCv, useParticipantReferrals, useProfile } from './queries';
import {
  isOpenStage,
  placementIndicators,
  verificationCounts,
  type TabId,
} from './readiness';
import { monthsText, shortDate, type Detail } from './types';

/**
 * One screen answering "where does this youth stand?". Three separate things, never blended
 * into one score: how complete the CV is, how much staff have checked, and which plain
 * placement steps are still open.
 */
export function OverviewTab({
  p,
  go,
}: {
  p: Detail;
  go: (tab: TabId) => void;
}) {
  const { can } = useAuth();
  const canProfile = can('participants.view_profile');
  const cv = useCv(p.id);
  const profile = useProfile(p.id);
  const refs = useParticipantReferrals(p.id);
  const rows = refs.data?.results ?? [];
  const open = rows.filter((r) => isOpenStage(r.stage));

  if (canProfile && (cv.isError || profile.isError))
    return (
      <ErrorState
        error={cv.error ?? profile.error}
        onRetry={() => {
          void cv.refetch();
          void profile.refetch();
        }}
      />
    );
  if (canProfile && (!cv.data || !profile.data)) return <LoadingState />;

  const prof = profile.data;
  const doc = cv.data;
  const counts = prof ? verificationCounts(prof) : null;
  const indicators =
    doc && prof
      ? placementIndicators(doc, prof, refs.data ? open.length : null)
      : [];
  const latestWork = prof?.experience
    .slice()
    .sort((a, b) => (b.start_date ?? '').localeCompare(a.start_date ?? ''))[0];
  const topEducation = prof?.qualifications[0];
  const enrolment = p.enrollments[0];

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        {doc && (
          <DataCard title="CV profile">
            <div className="space-y-3 p-5 text-sm">
              {doc.summary ? (
                <p className="break-words whitespace-pre-line">{doc.summary}</p>
              ) : (
                <p className="text-muted-foreground">
                  No professional summary yet.
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {doc.skills.slice(0, 8).map((s) => (
                  <Badge key={s.name} variant="secondary" appearance="light">
                    {s.name}
                  </Badge>
                ))}
                {doc.skills.length === 0 && (
                  <span className="text-muted-foreground">
                    No skills listed.
                  </span>
                )}
              </div>
              <dl className="grid gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-muted-foreground">
                    Highest education
                  </dt>
                  <dd>
                    {topEducation
                      ? [topEducation.level, topEducation.institution]
                          .filter(Boolean)
                          .join(', ')
                      : 'Not recorded'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">
                    Most recent work
                  </dt>
                  <dd>
                    {latestWork
                      ? `${latestWork.role_title}${latestWork.employer_name ? `, ${latestWork.employer_name}` : ''} (${monthsText(latestWork.months)})`
                      : prof?.readiness.no_work_experience
                        ? 'No work experience yet'
                        : 'Not recorded'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">
                    Available from
                  </dt>
                  <dd>
                    {prof?.readiness.available_from
                      ? shortDate(prof.readiness.available_from)
                      : 'Not recorded'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">
                    Preferred roles
                  </dt>
                  <dd>
                    {prof?.readiness.preferred_roles.join(', ') ||
                      'Not recorded'}
                  </dd>
                </div>
              </dl>
            </div>
          </DataCard>
        )}

        <DataCard
          title="Referrals"
          toolbar={
            can('referrals.view') && (
              <Button size="sm" variant="ghost" onClick={() => go('referrals')}>
                See all
              </Button>
            )
          }
        >
          <div className="p-5 text-sm">
            {!can('referrals.view') ? (
              <p className="text-muted-foreground">
                Your role cannot see referrals.
              </p>
            ) : refs.isError ? (
              <ErrorState
                error={refs.error}
                onRetry={() => void refs.refetch()}
              />
            ) : !refs.data ? (
              <LoadingState rows={2} />
            ) : rows.length === 0 ? (
              <p className="text-muted-foreground">
                Not referred to any opportunity yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {rows.slice(0, 3).map((r) => (
                  <li
                    key={r.id}
                    className="flex flex-wrap items-center justify-between gap-2"
                  >
                    <Link
                      className="font-medium hover:text-primary"
                      to={`/referrals/${r.id}`}
                    >
                      {r.opportunity}{' '}
                      <span className="font-normal text-muted-foreground">
                        {r.employer}
                      </span>
                    </Link>
                    <StatusBadge status={r.stage} label={r.stage_label} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </DataCard>

        {can('participants.view_profile') && (
          <DataCard title="Recent activity">
            <div className="p-5">
              <ActivityFeed id={p.id} referrals={rows} limit={5} />
            </div>
          </DataCard>
        )}
      </div>

      <div className="space-y-5">
        {doc && (
          <DataCard title="CV completeness">
            <div className="space-y-3 p-5 text-sm">
              <p className="text-2xl font-semibold">
                {doc.completeness.percent}%
              </p>
              <div
                role="progressbar"
                aria-valuenow={doc.completeness.percent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="CV completeness"
                className="h-2 overflow-hidden rounded-full bg-muted"
              >
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${doc.completeness.percent}%` }}
                />
              </div>
              {doc.completeness.missing.length > 0 ? (
                <ul className="space-y-1 text-muted-foreground">
                  {doc.completeness.missing.map((m) => (
                    <li key={m.key}>{m.label}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">Essentials in place.</p>
              )}
            </div>
          </DataCard>
        )}

        {counts && (
          <DataCard title="Verification">
            <div className="space-y-2 p-5 text-sm">
              {counts.total === 0 ? (
                <p className="text-muted-foreground">Nothing to verify yet.</p>
              ) : (
                <>
                  <p>
                    <span className="text-2xl font-semibold">
                      {counts.verified}
                    </span>{' '}
                    of {counts.total} entries verified
                  </p>
                  {counts.needs_reassessment > 0 && (
                    <p className="text-warning">
                      {counts.needs_reassessment} changed since checked
                    </p>
                  )}
                </>
              )}
              <Button size="sm" variant="outline" onClick={() => go('skills')}>
                Open verification
              </Button>
            </div>
          </DataCard>
        )}

        {indicators.length > 0 && (
          <DataCard
            title="Placement readiness"
            description="What is still open. Not a score."
          >
            <ul className="divide-y divide-border text-sm">
              {indicators.map((i) => (
                <li key={i.key} className="flex items-start gap-2 p-3">
                  {i.done ? (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
                  ) : (
                    <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className={i.done ? '' : 'font-medium'}>{i.label}</p>
                    {!i.done && i.hint && (
                      <p className="text-xs break-words text-muted-foreground">
                        {i.hint}
                      </p>
                    )}
                  </div>
                  {!i.done && (
                    <Button size="sm" variant="ghost" onClick={() => go(i.tab)}>
                      Fix
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </DataCard>
        )}

        {!canProfile && (
          <EmptyState
            title="CV details hidden"
            hint="Your role cannot view skills and readiness. Ask an administrator if you need access."
          />
        )}
        {enrolment && (
          <DataCard title="Project">
            <p className="p-5 text-sm">
              {[enrolment.project, enrolment.cohort, enrolment.course]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </DataCard>
        )}
      </div>
    </div>
  );
}
