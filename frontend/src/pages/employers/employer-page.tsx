import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useParams, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ActivityTimeline } from '@/components/shared/activity-timeline';
import { DetailList, Section } from '@/components/shared/info-card';
import { DialogShell } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { EmployerEvidence } from './employer-evidence';
import { EmployerFeedback } from './employer-feedback';
import {
  EmployerForm,
  EmployerValues,
  names,
  Option,
  Options,
} from './employer-form';
import { PeoplePanel, staffEndpoints } from './people-panel';

interface Detail extends EmployerValues {
  id: string;
  sectors: Option[];
  counties: Option[];
}
interface Event {
  at: string;
  actor: string;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}
interface OppRow {
  id: string;
  title: string;
  kind: string;
  status: string;
  positions: number;
  closing_date: string | null;
}

export function EmployerPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const canEdit = can('employers.edit');
  const [query] = useSearchParams();
  const [editing, setEditing] = useState(canEdit && query.get('edit') === '1');

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['employer', id] });
    void qc.invalidateQueries({ queryKey: ['employer-history', id] });
  };
  const q = useQuery({
    queryKey: ['employer', id],
    queryFn: () => api<Detail>(`/employers/${id}`),
    retry: false,
  });
  const history = useQuery({
    queryKey: ['employer-history', id],
    queryFn: () => api<Event[]>(`/employers/${id}/history`),
  });
  const opps = useQuery({
    queryKey: ['employer-opportunities', id],
    queryFn: () =>
      api<{ total: number; results: OppRow[] }>(
        `/opportunities?employer=${id}`,
      ),
  });
  const options = useQuery({
    queryKey: ['employer-filters'],
    queryFn: () => api<Options>('/employers/filters'),
    enabled: editing,
  });
  const save = useMutation({
    mutationFn: ({ v, confirm }: { v: EmployerValues; confirm: boolean }) =>
      api(`/employers/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ ...v, confirm_duplicate: confirm }),
      }),
    onSuccess: () => {
      setEditing(false);
      toast.success('Employer updated.');
      refresh();
    },
  });
  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Employer not found"
            hint="It may have been removed or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        <Link className="text-primary" to="/employers">
          Back to employers
        </Link>
      </div>
    );
  }
  const e = q.data;
  if (!e) return <LoadingState />;

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{e.name} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Employers', to: '/employers' }, { label: e.name }]}
        title={e.name}
        badges={<StatusBadge status={e.status} />}
        meta={
          <>
            {e.sectors.length > 0 && <span>{names(e.sectors)}</span>}
            {e.counties.length > 0 && <span>{names(e.counties)}</span>}
          </>
        }
        actions={
          canEdit && (
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil /> Edit employer
            </Button>
          )
        }
      />

      {editing && (
        <DialogShell
          open
          onOpenChange={(o) => !o && setEditing(false)}
          title="Edit employer"
        >
          <EmployerForm
            initial={{
              name: e.name,
              sector_ids: e.sector_ids,
              county_ids: e.county_ids,
              sub_county: e.sub_county,
              address: e.address,
              website: e.website,
              status: e.status,
              notes: e.notes,
            }}
            employerId={e.id}
            options={options.data}
            onCancel={() => setEditing(false)}
            onSave={async (v, confirm) => {
              await save.mutateAsync({ v, confirm });
            }}
          />
        </DialogShell>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Section title="Employer information">
            <DetailList
              items={[
                { label: 'Status', value: <StatusBadge status={e.status} /> },
                { label: 'Industry / Sector', value: names(e.sectors) },
                { label: 'Counties', value: names(e.counties) },
                { label: 'Sub-county', value: e.sub_county },
                { label: 'Address', value: e.address },
                {
                  label: 'Website',
                  value: e.website,
                },
                { label: 'Notes', value: e.notes },
              ]}
            />
          </Section>

          <PeoplePanel
            endpoints={staffEndpoints(e.id)}
            canEdit={canEdit}
            canAccess={can('employers.invite_user')}
          />

          {(opps.data?.results.length ?? 0) > 0 && (
            <Section
              title="Opportunities"
              description={`${opps.data?.total} from this employer`}
              flush
            >
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead>Title</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Positions</TableHead>
                      <TableHead>Closes</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {opps.data?.results.map((o) => (
                      <TableRow key={o.id}>
                        <TableCell>
                          <Link
                            className="font-medium hover:text-primary"
                            to={`/opportunities/${o.id}`}
                          >
                            {o.title}
                          </Link>
                        </TableCell>
                        <TableCell className="capitalize">{o.kind}</TableCell>
                        <TableCell>{o.positions}</TableCell>
                        <TableCell>{o.closing_date ?? ''}</TableCell>
                        <TableCell>
                          <StatusBadge status={o.status} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </Section>
          )}
        </div>

        <EmployerEvidence id={e.id} />

        <EmployerFeedback id={e.id} />

        <Section title="Activity">
          {history.isPending ? (
            <LoadingState rows={3} />
          ) : (
            <ActivityTimeline events={history.data ?? []} />
          )}
        </Section>
      </div>
    </div>
  );
}
