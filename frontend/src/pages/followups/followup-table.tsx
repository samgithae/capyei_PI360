import { Link } from 'react-router';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { StatusBadge } from '@/components/shared/status-badge';
import { OverdueBadge, type FollowUpRow } from './followup-shared';

/** Follow-up rows, soonest due first. `showYouth` is off on a youth's own profile. */
export function FollowUpTable({
  rows,
  showYouth = true,
}: {
  rows: FollowUpRow[];
  showYouth?: boolean;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted/40">
          {showYouth && <TableHead>Youth</TableHead>}
          <TableHead>Check-in</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Due</TableHead>
          <TableHead>Owner</TableHead>
          <TableHead>Next action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((f) => (
          <TableRow key={f.id}>
            {showYouth && (
              <TableCell>
                <Link
                  className="font-medium text-foreground hover:text-primary"
                  to={`/followups/${f.id}`}
                >
                  {f.participant}
                </Link>
                <p className="text-xs text-muted-foreground">{f.employer}</p>
              </TableCell>
            )}
            <TableCell>
              {showYouth ? (
                f.label
              ) : (
                <Link
                  className="font-medium text-foreground hover:text-primary"
                  to={`/followups/${f.id}`}
                >
                  {f.label}
                </Link>
              )}
              <p className="text-xs text-muted-foreground">{f.kind_label}</p>
            </TableCell>
            <TableCell>
              <StatusBadge status={f.status} label={f.status_label} />
            </TableCell>
            <TableCell>
              {f.due_date}
              <OverdueBadge row={f} />
            </TableCell>
            <TableCell>{f.assigned_to}</TableCell>
            <TableCell>
              {f.next_action ? (
                <>
                  {f.next_action}
                  {f.next_action_date && (
                    <p className="text-xs text-muted-foreground">
                      {f.next_action_date}
                    </p>
                  )}
                </>
              ) : (
                <span className="text-muted-foreground">None</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
