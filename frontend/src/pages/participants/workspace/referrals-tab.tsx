import { useAuth } from '@/auth/auth-context';
import { YouthCasework } from '@/pages/cases/youth-casework';
import { Send } from 'lucide-react';
import { Link } from 'react-router';
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
import { useParticipantReferrals } from './queries';
import { shortDate, type Detail } from './types';

/** Every referral of this youth with its stage, plus placements that came out of them. */
export function ReferralsTab({
  p,
  onRefer,
}: {
  p: Detail;
  onRefer: () => void;
}) {
  const { can } = useAuth();
  const q = useParticipantReferrals(p.id);
  const canRefer = can('referrals.edit') && !p.archived;
  if (!can('referrals.view'))
    return (
      <EmptyState
        title="Not available for your role"
        hint="Your role cannot see referrals."
      />
    );
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const rows = q.data.results;
  const placed = rows.filter((r) => r.stage === 'placed');

  return (
    <div className="space-y-5">
      {placed.length > 0 && (
        <DataCard title="Placement">
          <ul className="divide-y divide-border text-sm">
            {placed.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap justify-between gap-2 p-4"
              >
                <span className="font-medium break-words">
                  {r.opportunity}
                  <span className="font-normal text-muted-foreground">
                    {' '}
                    at {r.employer}
                  </span>
                </span>
                <span className="text-muted-foreground">
                  Placed {shortDate(r.closed_at ?? r.updated_at)}
                </span>
              </li>
            ))}
          </ul>
        </DataCard>
      )}
      <DataCard
        title="Referral history"
        toolbar={
          canRefer && (
            <Button size="sm" onClick={onRefer}>
              <Send /> Refer to Opportunity
            </Button>
          )
        }
      >
        {rows.length === 0 ? (
          <div className="p-5">
            <EmptyState
              title="Not referred to any opportunity yet"
              hint="Referrals made for this youth will appear here with their stage."
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Opportunity</TableHead>
                <TableHead>Employer</TableHead>
                <TableHead>County</TableHead>
                <TableHead>Sector</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Referred</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/referrals/${r.id}`}
                    >
                      {r.opportunity}
                    </Link>
                  </TableCell>
                  <TableCell>{r.employer}</TableCell>
                  <TableCell>
                    {(r.opportunity_counties ?? []).join(', ')}
                  </TableCell>
                  <TableCell>
                    {(r.opportunity_sectors ?? []).join(', ')}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={r.stage} label={r.stage_label} />
                    {r.reason && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {r.reason}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>{shortDate(r.referred_at)}</TableCell>
                  <TableCell>{shortDate(r.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DataCard>
      <YouthCasework id={p.id} name={p.name} archived={p.archived} />
    </div>
  );
}
