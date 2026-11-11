import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { api, ApiError } from '@/lib/api';
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
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

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
  const q = useQuery({
    queryKey: ['participant', id],
    queryFn: () => api<Detail>(`/participants/${id}`),
    retry: false,
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
      <PageHeader crumbs={[{ label: p.name }]} title={p.name} />
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
