import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { api, ApiError } from '@/lib/api';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard } from '@/components/data-card';
import { RowActions } from '@/components/shared/bulk';
import { DetailList, Section } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { when, type RuleSetDetail } from './rules-shared';

/** One rule set and all its versions, newest first. */
export function RuleSetPage() {
  const { id } = useParams();
  const q = useQuery({
    queryKey: ['rule-set', id],
    queryFn: () => api<RuleSetDetail>(`/rules/${id}`),
    retry: false,
  });

  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Rule set not found"
            hint="The link may be wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        <Link className="text-primary" to="/rules">
          Back to rules
        </Link>
      </div>
    );
  }
  const r = q.data;
  if (!r) return <LoadingState />;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>{`${r.name} | PI 360`}</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Rules', to: '/rules' }, { label: r.name }]}
        title={r.name}
        description={r.purpose || undefined}
        meta={
          <>
            <span>{r.module_label}</span>
            <span>Code {r.code}</span>
          </>
        }
      />
      <Section title="In force now">
        {r.active ? (
          <DetailList
            items={[
              {
                label: 'Version',
                value: (
                  <Link
                    className="text-primary hover:underline"
                    to={`/rules/versions/${r.active.id}`}
                  >
                    Version {r.active.number}
                  </Link>
                ),
              },
              { label: 'In force since', value: when(r.active.effective_from) },
              { label: 'Approved by', value: r.active.approved_by },
              { label: 'Factors', value: String(r.active.factors) },
            ]}
          />
        ) : (
          <EmptyState
            title="No version is in force"
            hint="Nothing is worked out from this rule set until a version is approved and activated."
          />
        )}
      </Section>
      <DataCard
        title="Versions"
        description="A version in force is never edited. To change the rules, copy a version, edit the copy and send it for review."
      >
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead>Version</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>What changed</TableHead>
              <TableHead>Factors</TableHead>
              <TableHead>Awaiting decision</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>In force from</TableHead>
              <TableHead className="w-12">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {r.versions.map((v) => (
              <TableRow key={v.id}>
                <TableCell>
                  <Link
                    className="font-medium text-foreground hover:text-primary"
                    to={`/rules/versions/${v.id}`}
                  >
                    Version {v.number}
                  </Link>
                </TableCell>
                <TableCell>
                  <StatusBadge status={v.status} label={v.status_label} />
                </TableCell>
                <TableCell className="max-w-xs whitespace-normal">
                  {v.change_notes || (
                    <span className="text-muted-foreground">-</span>
                  )}
                </TableCell>
                <TableCell>{v.factors}</TableCell>
                <TableCell>{v.waiting || 'None'}</TableCell>
                <TableCell>
                  {v.created_by || 'System'}
                  <p className="text-xs text-muted-foreground">
                    {when(v.created_at)}
                  </p>
                </TableCell>
                <TableCell>
                  {when(v.effective_from) || (
                    <span className="text-muted-foreground">-</span>
                  )}
                </TableCell>
                <TableCell>
                  <RowActions
                    label={`${r.name}, version ${v.number}`}
                    viewTo={`/rules/versions/${v.id}`}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </DataCard>
    </div>
  );
}
