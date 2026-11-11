import { type ReactNode } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Briefcase, Building2, FileUp, Users } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { api, type Health } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge, type Batch } from './imports/shared';

type Total = { total: number };

/** One Metronic-style KPI tile: icon chip, big number, label. Links to the list it counts. */
function Stat({
  icon,
  label,
  value,
  to,
}: {
  icon: ReactNode;
  label: string;
  value: number | undefined;
  to: string;
}) {
  return (
    <Link to={to} className="block">
      <Card className="transition-shadow hover:shadow-md">
        <CardContent className="flex items-center gap-4 p-5">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            {icon}
          </div>
          <div>
            <div className="text-2xl font-semibold leading-none text-foreground">
              {value ?? '...'}
            </div>
            <div className="mt-1.5 text-sm text-muted-foreground">{label}</div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

/** Home dashboard. Every figure is a live count from the same endpoints the list pages use,
 * and each tile only appears (and only fetches) if the user may see that list. */
export function OverviewPage() {
  const { can } = useAuth();
  const seeYouth = can('participants.view');
  const seeEmployers = can('employers.view');
  const seeImports = can('imports.run');

  const youth = useQuery({
    queryKey: ['overview', 'youth'],
    queryFn: () => api<Total>('/participants'),
    enabled: seeYouth,
  });
  const employers = useQuery({
    queryKey: ['overview', 'employers'],
    queryFn: () => api<Total>('/employers'),
    enabled: seeEmployers,
  });
  const openOpps = useQuery({
    queryKey: ['overview', 'opportunities-open'],
    queryFn: () => api<Total>('/opportunities?status=open'),
    enabled: seeEmployers,
  });
  const imports = useQuery({
    queryKey: ['import-batches'],
    queryFn: () => api<Batch[]>('/imports/batches'),
    enabled: seeImports,
  });
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health'),
    retry: false,
  });

  const recent = (imports.data ?? []).slice(0, 5);
  const awaiting = (imports.data ?? []).filter((b) =>
    ['uploaded', 'validated', 'approved'].includes(b.status),
  ).length;

  return (
    <>
      <Helmet>
        <title>Overview | PI 360</title>
      </Helmet>
      <div className="container-fluid space-y-5">
        <PageHeader
          crumbs={[{ label: 'Overview' }]}
          title="Overview"
          actions={
            <>
              <div className="flex items-center gap-2">
                <Badge
                  variant={
                    health.isError
                      ? 'destructive'
                      : health.data
                        ? 'success'
                        : 'secondary'
                  }
                  appearance="light"
                >
                  {health.isError
                    ? 'API unreachable'
                    : health.data
                      ? `API ${health.data.status} · v${health.data.version}`
                      : 'Checking API'}
                </Badge>
                {seeImports && (
                  <Button asChild size="sm">
                    <Link to="/imports/new">New import</Link>
                  </Button>
                )}
              </div>
            </>
          }
        />

        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {seeYouth && (
            <Stat
              icon={<Users className="size-5" />}
              label="Youth in the directory"
              value={youth.data?.total}
              to="/youth"
            />
          )}
          {seeEmployers && (
            <Stat
              icon={<Building2 className="size-5" />}
              label="Employers"
              value={employers.data?.total}
              to="/employers"
            />
          )}
          {seeEmployers && (
            <Stat
              icon={<Briefcase className="size-5" />}
              label="Open opportunities"
              value={openOpps.data?.total}
              to="/opportunities?status=open"
            />
          )}
          {seeImports && (
            <Stat
              icon={<FileUp className="size-5" />}
              label="Imports not yet loaded"
              value={imports.data ? awaiting : undefined}
              to="/imports"
            />
          )}
        </div>

        {seeImports && (
          <DataCard
            title="Recent imports"
            toolbar={
              <Button asChild variant="outline" size="sm">
                <Link to="/imports">View all</Link>
              </Button>
            }
          >
            {recent.length === 0 ? (
              <p className="p-5 text-sm text-muted-foreground">
                {imports.isPending
                  ? 'Loading...'
                  : 'No imports yet. Upload a trainee file to load participants in bulk.'}
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40">
                    <TableHead>File</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Rows</TableHead>
                    <TableHead>Uploaded</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recent.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell>
                        <Link
                          className="font-medium text-foreground hover:text-primary"
                          to={`/imports/${b.id}`}
                        >
                          {b.file_name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={b.status} />
                      </TableCell>
                      <TableCell>{b.counts.total ?? 0}</TableCell>
                      <TableCell>
                        {new Date(b.created_at).toLocaleString()}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </DataCard>
        )}
      </div>
    </>
  );
}
