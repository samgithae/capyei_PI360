import { CapabilityProfile } from '@/pages/participants/capability-profile';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { DataCard } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { ErrorState, LoadingState } from '@/components/states';

interface Me {
  name: string;
  consent: { version: string; text: string; given: boolean };
}

/** A youth's own page: the consent notice first, then their skills and availability. */
export function PortalPage() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['youth-me'],
    queryFn: () => api<Me>('/youth/me'),
    retry: false,
  });
  const agree = useMutation({
    mutationFn: (version: string) => post('/youth/consent', { version }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['youth-me'] });
      void qc.invalidateQueries({ queryKey: ['participant-profile', 'self'] });
    },
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError || !q.data)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  const me = q.data;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>My profile</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'My profile' }]}
        title={`Hello, ${me.name}`}
      />
      {!me.consent.given ? (
        <DataCard title="Before you start">
          <div className="space-y-3 p-5 text-sm">
            <p>{me.consent.text}</p>
            <Button
              disabled={agree.isPending}
              onClick={() => agree.mutate(me.consent.version)}
            >
              I understand and agree
            </Button>
            {agree.error && (
              <p role="alert" className="text-destructive">
                {agree.error instanceof ApiError
                  ? agree.error.message
                  : 'Could not save.'}
              </p>
            )}
          </div>
        </DataCard>
      ) : (
        <CapabilityProfile id="me" self />
      )}
    </div>
  );
}
