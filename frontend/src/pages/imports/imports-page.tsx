import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
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
    <Button asChild size="sm">
      <Link to="/imports/new">New import</Link>
    </Button>
  );

  return (
    <>
      <Helmet>
        <title>Imports - PI 360</title>
      </Helmet>
      <div className="container-fluid space-y-5">
        <Toolbar>
          <ToolbarHeading>
            <ToolbarPageTitle text="Imports" />
          </ToolbarHeading>
          {newButton}
        </Toolbar>
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
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1">File</th>
                <th>Status</th>
                <th>Rows</th>
                <th>Create / update / blocked / skipped</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((b) => (
                <tr key={b.id} className="border-t">
                  <td className="py-1.5">
                    <Link
                      className="font-medium underline"
                      to={`/imports/${b.id}`}
                    >
                      {b.file_name}
                    </Link>
                  </td>
                  <td>
                    <StatusBadge status={b.status} />
                  </td>
                  <td>{b.counts.total ?? 0}</td>
                  <td>
                    {b.counts.create ?? 0} / {b.counts.update ?? 0} /{' '}
                    {b.counts.held ?? 0} / {b.counts.skip ?? 0}
                  </td>
                  <td>{new Date(b.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
