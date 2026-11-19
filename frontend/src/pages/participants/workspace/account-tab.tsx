import { useAuth } from '@/auth/auth-context';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard, ParticipantStatus } from '@/components/data-card';
import { InviteCard } from '../invite-card';
import { ActivityFeed } from './activity';
import { ConsentCard } from './consent-card';
import { useParticipantReferrals } from './queries';
import type { Detail } from './types';

/** One labelled value; an empty one says so, so a missing field is visible rather than hidden. */
function Fact({
  label,
  value,
  capitalise,
}: {
  label: string;
  value?: string | null;
  capitalise?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={capitalise ? 'capitalize' : undefined}>
        {value || <span className="text-muted-foreground">Not recorded</span>}
      </dd>
    </div>
  );
}

/** Staff-side record: personal details, programme history, sign-in account and change history. */
export function AccountTab({ p }: { p: Detail }) {
  const { can } = useAuth();
  const refs = useParticipantReferrals(p.id);
  const current = p.residences.find((r) => r.current);
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Personal details</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <Fact label="Full name" value={p.name} />
            <Fact label="First name" value={p.given_name} />
            <Fact label="Middle name" value={p.family_name} />
            <Fact label="Last name" value={p.other_names} />
            <Fact label="Gender" value={p.gender} capitalise />
            <Fact label="Status" value={p.status} capitalise />
            <Fact label="Date of birth" value={p.date_of_birth} />
            <Fact
              label="Age"
              value={
                p.age === null
                  ? ''
                  : `${p.age}${!p.date_of_birth && p.age_basis_date ? ` (as at ${p.age_basis_date})` : ''}`
              }
            />
            <Fact label="Home county" value={p.county} />
            <Fact label="Current county" value={current?.county} />
            <Fact label="Current sub-county" value={current?.sub_county} />
            <Fact label="Current ward" value={current?.ward} />
          </dl>
          {p.residences.some((r) => !r.current) && (
            <div className="mt-4 text-sm">
              <p className="mb-1 font-medium">Previous addresses</p>
              <ul className="list-disc space-y-0.5 ps-5 text-muted-foreground">
                {p.residences
                  .filter((r) => !r.current)
                  .map((r, i) => (
                    <li key={i}>
                      {[r.county, r.sub_county, r.ward]
                        .filter(Boolean)
                        .join(', ') || 'Not recorded'}
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      {p.consent && <ConsentCard p={p} consent={p.consent} />}

      {p.contacts && (
        <Card>
          <CardHeader>
            <CardTitle>Contact</CardTitle>
          </CardHeader>
          <CardContent>
            {p.contacts.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No contact details recorded.
              </p>
            ) : (
              <ul className="space-y-1 text-sm break-words">
                {p.contacts.map((c, i) => (
                  <li key={i}>
                    {c.kind}: {c.value}
                    {c.primary && ' (primary)'}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      <DataCard title="Programme and enrollment history">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead>Programme</TableHead>
              <TableHead>Cohort</TableHead>
              <TableHead>Course</TableHead>
              <TableHead>Institution</TableHead>
              <TableHead>Enrollment no.</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Enrolled on</TableHead>
              <TableHead>Completed on</TableHead>
              <TableHead>Exit reason</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {p.enrollments.map((e) => (
              <TableRow key={e.id}>
                <TableCell>{e.programme}</TableCell>
                <TableCell>{e.cohort}</TableCell>
                <TableCell>{e.course}</TableCell>
                <TableCell>{e.institution}</TableCell>
                <TableCell>{e.enrollment_no}</TableCell>
                <TableCell>
                  <ParticipantStatus status={e.status} />
                </TableCell>
                <TableCell>{e.enrolled_on ?? ''}</TableCell>
                <TableCell>{e.completed_on ?? ''}</TableCell>
                <TableCell>{e.exit_reason ?? ''}</TableCell>
              </TableRow>
            ))}
            {p.enrollments.length === 0 && (
              <TableRow>
                <TableCell colSpan={9} className="text-muted-foreground">
                  Not enrolled in any programme.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </DataCard>

      {p.enrollments.some((e) => Object.keys(e.extra ?? {}).length > 0) && (
        <Card>
          <CardHeader>
            <CardTitle>Other details from the source file</CardTitle>
          </CardHeader>
          <CardContent>
            {p.enrollments.map((e) => (
              <dl
                key={e.id}
                className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[14rem_1fr]"
              >
                {Object.entries(e.extra ?? {}).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="break-words">{v}</dd>
                  </div>
                ))}
              </dl>
            ))}
          </CardContent>
        </Card>
      )}

      {can('participants.invite') && <InviteCard id={p.id} />}

      {can('participants.view_profile') && (
        <DataCard title="Activity">
          <div className="p-5">
            <ActivityFeed id={p.id} referrals={refs.data?.results} />
          </div>
        </DataCard>
      )}
    </div>
  );
}
