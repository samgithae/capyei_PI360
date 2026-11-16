import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { Card, CardContent } from '@/components/ui/card';
import { Section } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { Dashboard, EmployerMe } from './employer-types';

/** A figure that is also a link to the list it counts. */
function Figure({
  label,
  value,
  to,
}: {
  label: string;
  value: number;
  to: string;
}) {
  return (
    <Link
      to={to}
      className="block rounded-lg focus-visible:outline-2 focus-visible:outline-primary"
      aria-label={`${label}: ${value}. Show the list`}
    >
      <Card className="h-full transition-colors hover:border-primary">
        <CardContent className="space-y-1 p-4">
          <p className="text-2xl font-semibold text-mono">{value}</p>
          <p className="text-sm text-muted-foreground">{label}</p>
        </CardContent>
      </Card>
    </Link>
  );
}

/** Horizontal bars with the number written beside each, so nothing relies on colour or hover. */
function Bars({
  rows,
  unit,
}: {
  rows: { key: string; label: string; count: number; to?: string }[];
  unit: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li
          key={r.key}
          className="grid grid-cols-[9rem_1fr_3rem] items-center gap-3 text-sm"
        >
          {r.to ? (
            <Link to={r.to} className="truncate hover:text-primary">
              {r.label}
            </Link>
          ) : (
            <span className="truncate">{r.label}</span>
          )}
          <div
            className="h-2 rounded bg-muted"
            role="img"
            aria-label={`${r.label}: ${r.count} ${unit}`}
          >
            <div
              className="h-2 rounded bg-primary"
              style={{ width: `${(r.count / max) * 100}%` }}
            />
          </div>
          <span className="text-right tabular-nums">{r.count}</span>
        </li>
      ))}
    </ul>
  );
}

export function EmployerDashboardPage() {
  const me = useQuery({
    queryKey: ['employer-me'],
    queryFn: () => api<EmployerMe>('/employer/me'),
  });
  const q = useQuery({
    queryKey: ['employer-dashboard'],
    queryFn: () => api<Dashboard>('/employer/dashboard'),
  });
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const d = q.data;
  const r = d.referrals;
  const o = d.opportunities;
  const refs = (view: string) => `/employer/referrals?view=${view}`;
  const opps = (view: string) => `/employer/opportunities?view=${view}`;
  const noReferrals = r && Object.values(r.figures).every((n) => n === 0);

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Dashboard | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Dashboard' }]}
        title={me.data ? me.data.employer.name : 'Dashboard'}
        description={
          me.data ? `Signed in as ${me.data.member.name}.` : undefined
        }
      />

      {d.attention.length > 0 && (
        <Section title="Needs your attention">
          <ul className="space-y-2">
            {d.attention.map((a) => (
              <li key={a.kind}>
                <Link
                  to={a.link}
                  className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm hover:border-primary"
                >
                  <span>{a.text}</span>
                  <span aria-hidden>View</span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {r && (
        <section aria-label="Referrals" className="space-y-3">
          <h2 className="text-base font-semibold">Referrals</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Figure label="New" value={r.figures.new} to={refs('new')} />
            <Figure
              label="Under review"
              value={r.figures.review}
              to={refs('review')}
            />
            <Figure
              label="Interviews"
              value={r.figures.interviews}
              to={refs('interviews')}
            />
            <Figure
              label="Selected"
              value={r.figures.selected}
              to={refs('selected')}
            />
            <Figure
              label="Placed this year"
              value={r.figures.placed_ytd}
              to={refs('placed_ytd')}
            />
            <Figure
              label="Replied to"
              value={r.figures.replied}
              to={refs('replied')}
            />
            <Figure
              label={`Waiting over ${r.waiting_days} days`}
              value={r.figures.waiting}
              to={refs('waiting')}
            />
            <Card>
              <CardContent className="space-y-1 p-4">
                <p className="text-2xl font-semibold text-mono">
                  {r.reply_days_median === null
                    ? '-'
                    : `${r.reply_days_median} ${r.reply_days_median === 1 ? 'day' : 'days'}`}
                </p>
                <p className="text-sm text-muted-foreground">
                  Typical time to reply
                </p>
              </CardContent>
            </Card>
          </div>
        </section>
      )}

      {o && (
        <section aria-label="Opportunities" className="space-y-3">
          <h2 className="text-base font-semibold">Opportunities</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Figure label="Open" value={o.open} to={opps('open')} />
            <Figure
              label="Closing soon"
              value={o.closing_soon}
              to={opps('closing_soon')}
            />
            <Figure label="Expired" value={o.expired} to={opps('expired')} />
            <Figure
              label="Awaiting approval"
              value={o.awaiting}
              to={opps('awaiting')}
            />
            <Figure
              label="Sent back"
              value={o.declined}
              to={opps('declined')}
            />
          </div>
        </section>
      )}

      {r && !noReferrals && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Section
            title="Where referrals are"
            description="Everyone referred to you, by stage."
          >
            <Bars
              unit="referrals"
              rows={r.funnel.map((f) => ({
                key: f.stage,
                label: f.label,
                count: f.count,
                to: `/employer/referrals?stage=${f.stage}`,
              }))}
            />
          </Section>
          <Section
            title="New referrals each week"
            description="The last 12 weeks."
          >
            <Bars
              unit="new referrals"
              rows={r.trend.map((t) => ({
                key: t.week,
                label: new Date(t.week).toLocaleDateString(undefined, {
                  day: 'numeric',
                  month: 'short',
                }),
                count: t.count,
              }))}
            />
          </Section>
        </div>
      )}

      {r && r.per_opportunity.length > 0 && (
        <Section
          title="By opportunity"
          description="Referrals received for each."
        >
          <Bars
            unit="referrals"
            rows={r.per_opportunity.map((p) => ({
              key: p.opportunity_id,
              label: p.opportunity,
              count: p.total,
              to: `/employer/referrals?opportunity=${p.opportunity_id}`,
            }))}
          />
        </Section>
      )}

      {r && noReferrals && (
        <EmptyState
          title="No referrals yet"
          hint="When PI 360 refers young people to your opportunities, they appear here."
        />
      )}

      <Section title="Recent activity">
        {d.activity.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing yet.</p>
        ) : (
          <ul className="divide-y text-sm">
            {d.activity.map((a, i) => (
              <li key={i} className="flex flex-wrap justify-between gap-2 py-2">
                <Link to={a.link} className="hover:text-primary">
                  {a.text}
                </Link>
                {a.at && (
                  <span className="text-muted-foreground">
                    {new Date(a.at).toLocaleDateString()}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
