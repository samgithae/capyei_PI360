import { Link, useParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { api, ApiError } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';

interface Enrollment {
  id: string;
  programme: string;
  cohort: string;
  course: string;
  institution: string;
  enrollment_no: string;
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
  residences: { county: string; sub_county: string; ward: string; current: boolean }[];
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
        <p role="alert">
          {missing ? 'Participant not found.' : 'Could not load participant.'}
        </p>
        <Link className="text-primary" to="/youth">
          Back to directory
        </Link>
      </div>
    );
  }
  const p = q.data;
  if (!p) return null;

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{p.name} | PI 360</title>
      </Helmet>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>{p.name}</ToolbarPageTitle>
        </ToolbarHeading>
      </Toolbar>
      <div className="flex flex-wrap gap-2 text-sm">
        <Badge variant="secondary">{p.status}</Badge>
        <span>{p.gender}</span>
        {p.age !== null && <span>Age {p.age}</span>}
        {p.county && <span>{p.county}</span>}
      </div>

      <section>
        <h2 className="mb-2 font-semibold">Enrollment history</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-2">Programme</th>
              <th>Cohort</th>
              <th>Course</th>
              <th>Institution</th>
              <th>Enrollment no.</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {p.enrollments.map((e) => (
              <tr key={e.id} className="border-t">
                <td className="py-2">{e.programme}</td>
                <td>{e.cohort}</td>
                <td>{e.course}</td>
                <td>{e.institution}</td>
                <td>{e.enrollment_no}</td>
                <td>{e.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {p.contacts && (
        <section>
          <h2 className="mb-2 font-semibold">Contact</h2>
          <ul className="text-sm">
            {p.contacts.map((c, i) => (
              <li key={i}>
                {c.kind}: {c.value}
                {c.primary && ' (primary)'}
              </li>
            ))}
          </ul>
        </section>
      )}
      <Link className="text-primary text-sm" to="/youth">
        Back to directory
      </Link>
    </div>
  );
}
