import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard, useClientPage } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { StatusBadge, type Batch } from './shared';

/** Import history: every file ever uploaded, newest first. */
export function ImportsPage() {
  const { can } = useAuth();
  const list = useQuery({
    queryKey: ['import-batches'],
    queryFn: () => api<Batch[]>('/imports/batches'),
  });
  const newButton = can('imports.run') && (
    <div className="flex gap-2">
      {can('imports.commit') && (
        <Button asChild size="sm" variant="outline">
          <Link to="/imports/promote">Placements from extra data</Link>
        </Button>
      )}
      <Button asChild size="sm">
        <Link to="/imports/new">New import</Link>
      </Button>
    </div>
  );

  const paged = useClientPage(list.data ?? []);

  return (
    <>
      <Helmet>
        <title>Imports - PI 360</title>
      </Helmet>
      <div className="container-fluid space-y-5">
        <PageHeader
          crumbs={[{ label: 'Imports' }]}
          title="Imports"
          actions={<>{newButton}</>}
        />
        {list.isPending && <LoadingState />}
        {list.isError && (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        )}
        {list.data && list.data.length === 0 && (
          <EmptyState
            title="No imports yet"
            hint="Upload a trainee file to load participants in bulk."
            action={newButton}
          />
        )}
        {list.data && list.data.length > 0 && (
          <DataCard title="Import history" footer={paged.pager}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Rows</TableHead>
                  <TableHead>Create / update / blocked / skipped</TableHead>
                  <TableHead>Uploaded</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.rows.map((b) => (
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
                      {b.counts.create ?? 0} / {b.counts.update ?? 0} /{' '}
                      {b.counts.held ?? 0} / {b.counts.skip ?? 0}
                    </TableCell>
                    <TableCell>
                      {new Date(b.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </DataCard>
        )}
      </div>
    </>
  );
}
