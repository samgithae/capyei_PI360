import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { FollowUpTable } from '@/pages/followups/followup-table';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useSearchParams } from 'react-router';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard } from '@/components/data-card';
import { SummaryStatCard } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { InterventionDialog, type QueueData } from './case-shared';

/** Case management work queue (T-064): what needs doing, overdue first. */
export function CasesPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  // Default is "my work"; ?mine=0 shows everyone's inside the user's scope.
  const mine = params.get('mine') !== '0';
  const queue = useQuery({
    queryKey: ['case-queue', mine],
    queryFn: () => api<QueueData>(`/cases/queue?mine=${mine ? 1 : 0}`),
  });
  const q = queue.data;
  const setMine = (value: boolean) => {
    const next = new URLSearchParams(params);
    if (value) next.delete('mine');
    else next.set('mine', '0');
    setParams(next);
  };

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Cases | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Cases' }]}
        title="Cases"
        description="Support work for youth: what is overdue or due soon, referrals waiting on you, and youth who need a look."
        actions={
          <>
            <div
              role="group"
              aria-label="Whose work"
              className="inline-flex rounded-md border"
            >
              <Button
                variant={mine ? 'primary' : 'ghost'}
                aria-pressed={mine}
                onClick={() => setMine(true)}
              >
                Mine
              </Button>
              <Button
                variant={mine ? 'ghost' : 'primary'}
                aria-pressed={!mine}
                onClick={() => setMine(false)}
              >
                Everyone
              </Button>
            </div>
            {can('referrals.edit') && (
              <Button onClick={() => setAdding(true)}>
                <Plus /> Record intervention
              </Button>
            )}
          </>
        }
      />
      {adding && (
        <InterventionDialog
          open
          onOpenChange={setAdding}
          canAssign={can('caseload.reassign')}
        />
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <SummaryStatCard
          label="Open interventions"
          value={q?.counts.live}
          loading={queue.isPending}
        />
        <SummaryStatCard
          label="Overdue"
          value={q?.counts.overdue}
          loading={queue.isPending}
        />
        <SummaryStatCard
          label="Due in the next 7 days"
          value={q?.counts.due_soon}
          loading={queue.isPending}
        />
        <SummaryStatCard
          label="Awaiting verification"
          value={q?.counts.awaiting_verification}
          loading={queue.isPending}
        />
      </div>

      {queue.isError && (
        <ErrorState error={queue.error} onRetry={() => queue.refetch()} />
      )}
      {queue.isPending && <LoadingState />}

      {q && (
        <>
          <DataCard
            title="Interventions"
            description="Overdue first, then the soonest due."
          >
            {q.interventions.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="Nothing open"
                  hint={
                    mine
                      ? 'You have no open interventions. Switch to Everyone to see the wider queue.'
                      : 'No open interventions for the youth you can see.'
                  }
                />
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40">
                    <TableHead>Youth</TableHead>
                    <TableHead>Support</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Owner</TableHead>
                    <TableHead>Due</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {q.interventions.map((i) => (
                    <TableRow key={i.id}>
                      <TableCell>
                        <Link
                          className="font-medium text-foreground hover:text-primary"
                          to={`/cases/${i.id}`}
                        >
                          {i.participant}
                        </Link>
                      </TableCell>
                      <TableCell>
                        {i.title}
                        <p className="text-xs text-muted-foreground">
                          {i.need_label}
                        </p>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={i.status} label={i.status_label} />
                      </TableCell>
                      <TableCell>{i.owner}</TableCell>
                      <TableCell>
                        {i.due_date}
                        {i.overdue && (
                          <Badge
                            variant="destructive"
                            appearance="light"
                            className="ms-2"
                          >
                            Overdue
                          </Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </DataCard>

          <DataCard
            title={`Referrals waiting (${q.counts.referrals_waiting})`}
            description="Longest waiting first."
          >
            {q.referrals.length === 0 ? (
              <div className="p-5">
                <EmptyState title="No referrals are waiting on staff" />
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40">
                    <TableHead>Youth</TableHead>
                    <TableHead>Opportunity</TableHead>
                    <TableHead>Stage</TableHead>
                    <TableHead>Assigned to</TableHead>
                    <TableHead>Waiting</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {q.referrals.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>
                        <Link
                          className="font-medium text-foreground hover:text-primary"
                          to={`/referrals/${r.id}`}
                        >
                          {r.participant}
                        </Link>
                      </TableCell>
                      <TableCell>
                        {r.opportunity}
                        <p className="text-xs text-muted-foreground">
                          {r.employer}
                        </p>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={r.stage} label={r.stage_label} />
                      </TableCell>
                      <TableCell>{r.assigned_to}</TableCell>
                      <TableCell>{r.days_waiting} days</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </DataCard>

          {q.followups && (
            <DataCard
              title={`Follow-ups (${q.counts.followups_open ?? 0} open, ${q.counts.followups_overdue ?? 0} overdue)`}
              description="Check-ins after a placement, soonest due first."
              toolbar={
                <Button variant="outline" size="sm" asChild>
                  <Link to="/followups">All follow-ups</Link>
                </Button>
              }
            >
              {q.followups.length === 0 ? (
                <div className="p-5">
                  <EmptyState title="No follow-ups to do" />
                </div>
              ) : (
                <FollowUpTable rows={q.followups} />
              )}
            </DataCard>
          )}

          {q.placements_to_verify !== null && (
            <DataCard title="Placements to verify">
              <p className="p-5 text-sm">
                {q.placements_to_verify === 0 ? (
                  'Every placement has been verified.'
                ) : (
                  <>
                    {q.placements_to_verify} placement
                    {q.placements_to_verify === 1 ? '' : 's'} nobody has
                    verified yet.{' '}
                    <Link
                      className="font-medium text-primary hover:underline"
                      to="/placements?state=unverified"
                    >
                      Review them
                    </Link>
                  </>
                )}
              </p>
            </DataCard>
          )}

          {q.flags && (
            <DataCard
              title={`Youth who need a look (${q.flags.total})`}
              description="Flagged by the support rules the administrator sets."
            >
              {q.flags.items.length === 0 ? (
                <div className="p-5">
                  <EmptyState title="No youth are flagged" />
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead>Youth</TableHead>
                      <TableHead>Why</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {q.flags.items.map((f) => (
                      <TableRow key={f.participant_id}>
                        <TableCell>
                          <Link
                            className="font-medium text-foreground hover:text-primary"
                            to={`/youth/${f.participant_id}`}
                          >
                            {f.name}
                          </Link>
                        </TableCell>
                        <TableCell>
                          <ul className="space-y-0.5 text-sm">
                            {f.flags.map((x) => (
                              <li key={x.code}>
                                <span className="font-medium">{x.label}</span>
                                <span className="text-muted-foreground">
                                  {' '}
                                  {x.detail}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </DataCard>
          )}
        </>
      )}
    </div>
  );
}
