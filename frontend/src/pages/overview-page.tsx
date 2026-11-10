import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { api, type Health } from '@/lib/api';
import {
  Toolbar,
  ToolbarDescription,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
import { ErrorState, LoadingState, Notice } from '@/components/states';

export function OverviewPage() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health'),
    retry: false,
  });

  return (
    <div className="container-fluid">
      <Helmet>
        <title>Overview | PI 360</title>
      </Helmet>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>Overview</ToolbarPageTitle>
          <ToolbarDescription>
            Sprint 0 skeleton. Dashboard content follows the design sign-off.
          </ToolbarDescription>
        </ToolbarHeading>
      </Toolbar>
      {health.isPending && <LoadingState rows={1} />}
      {health.isError && (
        <ErrorState error={health.error} onRetry={() => health.refetch()} />
      )}
      {health.data && (
        <Notice tone="info" title="API reachable">
          Status {health.data.status}, version {health.data.version}.
        </Notice>
      )}
    </div>
  );
}
