import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import {
  ReferDialog,
  type ReferralPage,
} from '@/pages/referrals/referral-shared';
import { useQuery } from '@tanstack/react-query';
import { Archive, ArchiveRestore, Pencil, Send } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
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
import { useArchiveFlow } from '@/components/shared/bulk';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { CapabilityProfile } from './capability-profile';
import { EditParticipant } from './participant-edit';

interface Enrollment {
  id: string;
  programme: string;
  cohort: string;
  course: string;
  institution: string;
  enrollment_no: string;
  extra?: Record<string, string>;
  status: string;
  enrolled_on: string | null;
  completed_on: string | null;
}
interface Detail {
  archived: boolean;
  id: string;
  name: string;
  gender: string;
  age: number | null;
  status: string;
  county: string;
  enrollments: Enrollment[];
  residences: {
    county: string;
    sub_county: string;
    ward: string;
    current: boolean;
  }[];
  contacts?: { kind: string; value: string; primary: boolean }[];
}

export function ProfilePage() {
  const { id } = useParams();
  const { can } = useAuth();
  const [editing, setEditing] = useState(false);
  const [referring, setReferring] = useState(false);
  const archive = useArchiveFlow({
    path: '/participants',
    noun: 'participant',
    nounPlural: 'participants',
    queryKeys: ['participant', 'participants'],
  });
  const q = useQuery({
    queryKey: ['participant', id],
    queryFn: () => api<Detail>(`/participants/${id}`),
    retry: false,
  });

  // Runs only for people who may see referrals; `enabled: false` means no request at all.
  const referrals = useQuery({
    queryKey: ['referrals', 'participant', id],
    queryFn: () => api<ReferralPage>(`/referrals?participant=${id}`),
    enabled: can('referrals.view'),
  });

  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Participant not found"
            hint="It may have been removed or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        <Link className="text-primary" to="/youth">
          Back to directory
        </Link>
      </div>
    );
  }
  const p = q.data;
  if (!p) return <LoadingState />;

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{p.name} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: p.name }]}
        title={p.name}
        actions={
          <div className="flex gap-2">
            {can('records.archive') &&
              (p.archived ? (
                <Button
                  variant="outline"
                  onClick={() => archive.request([p.id], false)}
                >
                  <ArchiveRestore /> Restore
                </Button>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => archive.request([p.id], true)}
                >
                  <Archive /> Archive
                </Button>
              ))}
            {can('referrals.edit') && !p.archived && (
              <Button variant="outline" onClick={() => setReferring(true)}>
                <Send /> Refer
              </Button>
            )}
            {can('participants.edit') && (
              <Button onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
            )}
          </div>
        }
      />
      {archive.dialog}
      <ReferDialog
        open={referring}
        onOpenChange={setReferring}
        participant={{ id: p.id, name: p.name }}
      />
      {p.archived && (
        <p className="rounded-md border border-border bg-muted/40 p-3 text-sm">
          This participant is archived and hidden from lists and reports.
        </p>
      )}
      {editing && (
        <EditParticipant id={p.id} onClose={() => setEditing(false)} />
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <ParticipantStatus status={p.status} />
        <span>{p.gender}</span>
        {p.age !== null && <span>Age {p.age}</span>}
        {p.county && <span>{p.county}</span>}
      </div>

      <DataCard title="Enrollment history">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead>Programme</TableHead>
              <TableHead>Cohort</TableHead>
              <TableHead>Course</TableHead>
              <TableHead>Institution</TableHead>
              <TableHead>Enrollment no.</TableHead>
              <TableHead>Status</TableHead>
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
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </DataCard>

      {can('participants.view_profile') && <CapabilityProfile id={p.id} />}

      {referrals.data && referrals.data.results.length > 0 && (
        <DataCard title="Referrals">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Opportunity</TableHead>
                <TableHead>Employer</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Referred</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {referrals.data.results.map((r) => (
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
                    <StatusBadge status={r.stage} label={r.stage_label} />
                  </TableCell>
                  <TableCell>{r.referred_at?.slice(0, 10) ?? ''}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </DataCard>
      )}

      {p.enrollments.some((e) => Object.keys(e.extra ?? {}).length > 0) && (
        <Card>
          <CardHeader>
            <CardTitle>Other details from the source file</CardTitle>
          </CardHeader>
          <CardContent>
            {p.enrollments.map((e) => (
              <dl
                key={e.id}
                className="grid grid-cols-[14rem_1fr] gap-x-4 gap-y-1 text-sm"
              >
                {Object.entries(e.extra ?? {}).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
              </dl>
            ))}
          </CardContent>
        </Card>
      )}

      {p.contacts && (
        <Card>
          <CardHeader>
            <CardTitle>Contact</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {p.contacts.map((c, i) => (
                <li key={i}>
                  {c.kind}: {c.value}
                  {c.primary && ' (primary)'}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
      <Link className="text-primary text-sm" to="/youth">
        Back to directory
      </Link>
    </div>
  );
}
