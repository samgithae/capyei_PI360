import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import type { FollowUpPage } from '@/pages/followups/followup-shared';
import { FollowUpTable } from '@/pages/followups/followup-table';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Link } from 'react-router';
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
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import {
  InterventionDialog,
  PlacementDialog,
  type InterventionPage,
  type PlacementPage,
} from './case-shared';
import { PlacementTable } from './placement-table';

/** The youth's support interventions and placement episodes, for the profile page.
 * Each card appears only for roles that may see it; the server also checks scope. */
export function YouthCasework({
  id,
  name,
  archived,
}: {
  id: string;
  name: string;
  archived: boolean;
}) {
  const { can } = useAuth();
  const [addingCase, setAddingCase] = useState(false);
  const [addingPlacement, setAddingPlacement] = useState(false);
  const cases = useQuery({
    queryKey: ['interventions', 'participant', id],
    queryFn: () => api<InterventionPage>(`/interventions?participant=${id}`),
  });
  const placements = useQuery({
    queryKey: ['placements', 'participant', id],
    queryFn: () => api<PlacementPage>(`/placements?participant=${id}`),
    enabled: can('placements.view'),
  });
  const followups = useQuery({
    queryKey: ['followups', 'participant', id],
    queryFn: () => api<FollowUpPage>(`/followups?participant=${id}&state=all`),
    enabled: can('placements.view'),
  });

  return (
    <>
      <DataCard
        title="Support interventions"
        toolbar={
          can('referrals.edit') &&
          !archived && (
            <Button size="sm" onClick={() => setAddingCase(true)}>
              <Plus /> Record intervention
            </Button>
          )
        }
      >
        {cases.isError && (
          <div className="p-5">
            <ErrorState error={cases.error} onRetry={() => cases.refetch()} />
          </div>
        )}
        {cases.isPending && (
          <div className="p-5">
            <LoadingState rows={2} />
          </div>
        )}
        {cases.data && cases.data.results.length === 0 && (
          <div className="p-5">
            <EmptyState
              title="No support recorded yet"
              hint="Record what support this youth needs and what will be done."
            />
          </div>
        )}
        {cases.data && cases.data.results.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Support</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Due</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cases.data.results.map((i) => (
                <TableRow key={i.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/cases/${i.id}`}
                    >
                      {i.title}
                    </Link>
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

      {can('placements.view') && (
        <DataCard
          title="Placement episodes"
          description="Each job, business or training spell. Ending one keeps it in the history."
          toolbar={
            can('placements.edit') &&
            !archived && (
              <Button size="sm" onClick={() => setAddingPlacement(true)}>
                <Plus /> Record placement
              </Button>
            )
          }
        >
          {placements.isError && (
            <div className="p-5">
              <ErrorState
                error={placements.error}
                onRetry={() => placements.refetch()}
              />
            </div>
          )}
          {placements.isPending && (
            <div className="p-5">
              <LoadingState rows={2} />
            </div>
          )}
          {placements.data && placements.data.results.length === 0 && (
            <div className="p-5">
              <EmptyState title="No placement episodes yet" />
            </div>
          )}
          {placements.data && placements.data.results.length > 0 && (
            <PlacementTable rows={placements.data.results} showYouth={false} />
          )}
        </DataCard>
      )}

      {can('placements.view') && (
        <DataCard
          title="Follow-ups"
          description="Check-ins after a placement starts. Each one records the attempts and the youth's answer."
        >
          {followups.isError && (
            <div className="p-5">
              <ErrorState
                error={followups.error}
                onRetry={() => followups.refetch()}
              />
            </div>
          )}
          {followups.isPending && (
            <div className="p-5">
              <LoadingState rows={2} />
            </div>
          )}
          {followups.data && followups.data.results.length === 0 && (
            <div className="p-5">
              <EmptyState
                title="No follow-ups yet"
                hint="They are scheduled when a placement with a start date is recorded or verified."
              />
            </div>
          )}
          {followups.data && followups.data.results.length > 0 && (
            <FollowUpTable rows={followups.data.results} showYouth={false} />
          )}
        </DataCard>
      )}

      {addingCase && (
        <InterventionDialog
          open
          onOpenChange={setAddingCase}
          participant={{ id, name }}
          canAssign={can('caseload.reassign')}
        />
      )}
      {addingPlacement && (
        <PlacementDialog
          open
          onOpenChange={setAddingPlacement}
          participant={{ id, name }}
        />
      )}
    </>
  );
}
