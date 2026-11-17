import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { Link } from 'react-router';
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
import {
  EndPlacementDialog,
  PlacementDialog,
  VerifyPlacementDialog,
  type PlacementRow,
} from './case-shared';

const day = (d: string | null) => (d ? d.slice(0, 10) : '');

/** Placement episodes as a table, with Edit, End and Verify for people who may change them.
 * Used by the Placements page and by the youth profile. Imported episodes cannot be edited
 * here (they are corrected by re-importing); they can still be ended and verified. */
export function PlacementTable({
  rows,
  showYouth = true,
}: {
  rows: PlacementRow[];
  showYouth?: boolean;
}) {
  const { can } = useAuth();
  const canEdit = can('placements.edit');
  const [edit, setEdit] = useState<PlacementRow | null>(null);
  const [end, setEnd] = useState<PlacementRow | null>(null);
  const [verify, setVerify] = useState<PlacementRow | null>(null);

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40">
            {showYouth && <TableHead>Youth</TableHead>}
            <TableHead>Pathway</TableHead>
            <TableHead>Employer or business</TableHead>
            <TableHead>Started</TableHead>
            <TableHead>Ended</TableHead>
            <TableHead>Status</TableHead>
            {canEdit && (
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={p.id}>
              {showYouth && (
                <TableCell>
                  <Link
                    className="font-medium text-foreground hover:text-primary"
                    to={`/youth/${p.participant_id}`}
                  >
                    {p.participant}
                  </Link>
                </TableCell>
              )}
              <TableCell>
                {p.pathway_label}
                {p.designation && (
                  <p className="text-xs text-muted-foreground">
                    {p.designation}
                  </p>
                )}
              </TableCell>
              <TableCell>
                {p.employer}
                {p.employer && !p.linked && (
                  <p className="text-xs text-muted-foreground">
                    Not matched to the register
                  </p>
                )}
              </TableCell>
              <TableCell>{day(p.start_date)}</TableCell>
              <TableCell>
                {day(p.end_date)}
                {p.exit_reason && (
                  <p className="text-xs text-muted-foreground">
                    {p.exit_reason}
                  </p>
                )}
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  <Badge
                    variant={p.current ? 'success' : 'secondary'}
                    appearance="light"
                  >
                    {p.current ? 'Current' : 'Ended'}
                  </Badge>
                  <Badge
                    variant={p.verified ? 'info' : 'warning'}
                    appearance="light"
                  >
                    {p.verified
                      ? `Verified${p.verification_source_label ? `: ${p.verification_source_label}` : ''}`
                      : 'Not verified'}
                  </Badge>
                  {p.imported && (
                    <Badge variant="secondary" appearance="light">
                      Imported
                    </Badge>
                  )}
                </div>
              </TableCell>
              {canEdit && (
                <TableCell>
                  <div className="flex flex-wrap justify-end gap-1">
                    {!p.imported && (
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label={`Edit placement of ${p.participant}`}
                        onClick={() => setEdit(p)}
                      >
                        Edit
                      </Button>
                    )}
                    {!p.end_date && (
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label={`End placement of ${p.participant}`}
                        onClick={() => setEnd(p)}
                      >
                        End
                      </Button>
                    )}
                    {!p.verified && (
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label={`Verify placement of ${p.participant}`}
                        onClick={() => setVerify(p)}
                      >
                        Verify
                      </Button>
                    )}
                  </div>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {edit && (
        <PlacementDialog
          open
          onOpenChange={(o) => !o && setEdit(null)}
          edit={edit}
        />
      )}
      {end && (
        <EndPlacementDialog
          open
          onOpenChange={(o) => !o && setEnd(null)}
          placement={end}
        />
      )}
      {verify && (
        <VerifyPlacementDialog
          open
          onOpenChange={(o) => !o && setVerify(null)}
          placement={verify}
        />
      )}
    </>
  );
}
