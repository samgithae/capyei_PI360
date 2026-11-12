import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, Navigate } from 'react-router';
import { api, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { DataCard } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { ErrorState, LoadingState } from '@/components/states';
import type { Journey, Notices } from './journey';
import { StepTracker } from './step-tracker';

interface Me {
  name: string;
  consent: { given: boolean };
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-2xl font-semibold">{value}</p>
        <p className="text-sm text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  );
}

/** The learner's home: where they are in the journey, at a glance. */
export function DashboardPage() {
  const me = useQuery({
    queryKey: ['youth-me'],
    queryFn: () => api<Me>('/youth/me'),
    retry: false,
  });
  const given = me.data?.consent.given === true;
  const j = useQuery({
    queryKey: ['youth-journey'],
    queryFn: () => api<Journey>('/youth/journey'),
    enabled: given,
    retry: false,
  });

  const qc = useQueryClient();
  const notices = useQuery({
    queryKey: ['youth-notices'],
    queryFn: () => api<Notices>('/youth/notices'),
    enabled: given,
    retry: false,
  });
  const markSeen = useMutation({
    mutationFn: () => post<Notices>('/youth/notices'),
    onSuccess: (n) => qc.setQueryData(['youth-notices'], n),
  });

  if (me.isError)
    return <ErrorState error={me.error} onRetry={() => void me.refetch()} />;
  if (!me.data) return <LoadingState />;
  // The notice comes first; it lives on the profile page.
  if (!given) return <Navigate to="/me/profile" replace />;
  if (j.isError)
    return <ErrorState error={j.error} onRetry={() => void j.refetch()} />;
  if (!j.data) return <LoadingState />;
  const { counts, latest, steps } = j.data;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>My dashboard</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'My dashboard' }]}
        title={`Hello, ${me.data.name}`}
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Counter label="Referred" value={counts.referred} />
        <Counter label="Interview" value={counts.interview} />
        <Counter label="Selected" value={counts.selected} />
        <Counter label="Placed" value={counts.placed} />
      </div>
      {notices.data && notices.data.items.length > 0 && (
        <DataCard
          title={
            notices.data.unread > 0
              ? `Updates (${notices.data.unread} new)`
              : 'Updates'
          }
        >
          <div className="space-y-2 p-5 text-sm">
            <ul className="space-y-1">
              {notices.data.items.slice(0, 5).map((n, i) => (
                <li key={i}>
                  <span className="text-muted-foreground">
                    {new Date(n.at).toLocaleDateString()}
                  </span>{' '}
                  · {n.text}
                </li>
              ))}
            </ul>
            {notices.data.unread > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => markSeen.mutate()}
              >
                Mark as read
              </Button>
            )}
          </div>
        </DataCard>
      )}
      <DataCard title="Latest opportunity">
        {latest ? (
          <div className="space-y-3 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <Link
                className="font-medium text-foreground hover:text-primary"
                to={`/me/opportunities/${latest.id}`}
              >
                {latest.opportunity}
              </Link>
              <span className="text-sm text-muted-foreground">
                {latest.employer}
              </span>
              <StatusBadge status={latest.stage} label={latest.stage_label} />
            </div>
            <StepTracker steps={steps} item={latest} />
            <Link className="text-sm text-primary" to="/me/opportunities">
              See all my opportunities
            </Link>
          </div>
        ) : (
          <p className="p-5 text-sm text-muted-foreground">
            You have not been referred to an opportunity yet. Keep your profile
            up to date so your officer can find the right fit.{' '}
            <Link className="text-primary" to="/me/profile">
              Update my profile
            </Link>
          </p>
        )}
      </DataCard>
    </div>
  );
}
