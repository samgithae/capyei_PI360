import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
} from '@/components/states';
import {
  ImportStepper,
  StatusBadge,
  type Batch,
  type Reconciliation,
} from './shared';

interface Row {
  row: number;
  outcome: string;
  match: string;
  source_key: string;
  errors: { field: string; message: string }[];
  warnings: { field: string; message: string }[];
}

const PAGE = 200;
const OUTCOMES: [string, string][] = [
  ['', 'All rows'],
  ['held', 'Blocked'],
  ['update', 'Will update'],
  ['create', 'Will create'],
  ['skip', 'Skipped'],
];
const OUTCOME_LABEL: Record<string, string> = {
  held: 'Blocked',
  update: 'Will update',
  create: 'Will create',
  skip: 'Skipped',
};
// Once a batch is loaded the same outcomes are past tense.
const LOADED_LABEL: Record<string, string> = {
  update: 'Updated',
  create: 'Created',
};

function errorText(e: unknown) {
  return e instanceof ApiError ? e.message : 'Something went wrong.';
}

function Count({
  label,
  value,
  hint,
}: {
  label: string;
  value?: number;
  hint: string;
}) {
  return (
    <div className="rounded-lg border p-3">
      <div className="text-2xl font-semibold">{value ?? 0}</div>
      <div className="text-sm font-medium">{label}</div>
      <div className="text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}

function RowsTable({ id, loaded }: { id: string; loaded: boolean }) {
  const [outcome, setOutcome] = useState('');
  const [offset, setOffset] = useState(0);
  const rows = useQuery({
    queryKey: ['import-rows', id, outcome, offset],
    queryFn: () =>
      api<{ total: number; rows: Row[] }>(
        `/imports/batches/${id}/rows?offset=${offset}${outcome ? `&outcome=${outcome}` : ''}`,
      ),
  });
  const total = rows.data?.total ?? 0;

  return (
    <section className="space-y-3">
      <div
        className="flex flex-wrap gap-2"
        role="tablist"
        aria-label="Filter rows"
      >
        {OUTCOMES.map(([value, base]) => {
          const label = (loaded && LOADED_LABEL[value]) || base;
          return (
            <Button
              key={value}
              size="sm"
              role="tab"
              aria-selected={outcome === value}
              variant={outcome === value ? 'primary' : 'outline'}
              onClick={() => {
                setOutcome(value);
                setOffset(0);
              }}
            >
              {label}
            </Button>
          );
        })}
      </div>
      {rows.isPending && <LoadingState />}
      {rows.isError && (
        <ErrorState error={rows.error} onRetry={() => rows.refetch()} />
      )}
      {rows.data && rows.data.rows.length === 0 && (
        <EmptyState title="No rows here" hint="Try another filter." />
      )}
      {rows.data && rows.data.rows.length > 0 && (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 w-14">Row</th>
                <th className="w-32">Result</th>
                <th className="w-40">Key</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.rows.map((r) => (
                <tr key={r.row} className="border-t align-top">
                  <td className="py-1.5">{r.row}</td>
                  <td>
                    <Badge
                      appearance="light"
                      variant={
                        r.outcome === 'held'
                          ? 'destructive'
                          : r.outcome === 'skip'
                            ? 'secondary'
                            : 'success'
                      }
                    >
                      {(loaded && LOADED_LABEL[r.outcome]) ||
                        OUTCOME_LABEL[r.outcome] ||
                        r.outcome}
                    </Badge>
                  </td>
                  <td>{r.source_key || '-'}</td>
                  <td className="space-y-0.5">
                    {r.errors.map((e, i) => (
                      <div key={`e${i}`}>
                        <span className="font-medium">Blocking</span>{' '}
                        {e.field && `${e.field}: `}
                        {e.message}
                      </div>
                    ))}
                    {r.warnings.map((e, i) => (
                      <div key={`w${i}`} className="text-muted-foreground">
                        <span className="font-medium">Warning</span>{' '}
                        {e.field && `${e.field}: `}
                        {e.message}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-2 text-sm">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              Previous
            </Button>
            <span>
              {offset + 1}-{Math.min(offset + PAGE, total)} of {total}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </section>
  );
}

function ReconciliationPanel({ id }: { id: string }) {
  const rec = useQuery({
    queryKey: ['import-reconciliation', id],
    queryFn: () => api<Reconciliation>(`/imports/batches/${id}/reconciliation`),
  });
  if (rec.isPending) return <LoadingState rows={3} />;
  if (rec.isError)
    return <ErrorState error={rec.error} onRetry={() => rec.refetch()} />;
  const r = rec.data;
  return (
    <section className="rounded-lg border p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-medium">Reconciliation</h2>
        <Badge
          appearance="light"
          variant={r.balanced ? 'success' : 'destructive'}
        >
          {r.balanced ? 'Balanced' : 'Not balanced'}
        </Badge>
        <Badge
          appearance="light"
          variant={r.controls_match ? 'success' : 'warning'}
        >
          {r.controls_match ? 'Cohort totals match' : 'Cohort totals differ'}
        </Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        Every source row lands in exactly one bucket: {r.source_rows} rows in
        the file, {r.accounted_for} accounted for.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        <Count label="Created" value={r.created} hint="new records" />
        <Count label="Updated" value={r.updated} hint="existing records" />
        <Count label="Skipped" value={r.skipped} hint="already loaded" />
        <Count label="Blocked" value={r.held} hint="not loaded" />
        <Count label="Rolled back" value={r.rolled_back} hint="reverted" />
        <Count
          label="To review"
          value={r.quarantined}
          hint="possible duplicates"
        />
      </div>
      {r.controls.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-1">Cohort</th>
              <th>In the file</th>
              <th>In PI 360</th>
              <th>Check</th>
            </tr>
          </thead>
          <tbody>
            {r.controls.map((c) => (
              <tr key={c.cohort} className="border-t">
                <td className="py-1">{c.cohort || '(none)'}</td>
                <td>{c.source}</td>
                <td>{c.pi360}</td>
                <td>{c.matches ? 'Matches' : 'Differs'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline">
          <a href={`/api/v1/imports/batches/${id}/reconciliation?download=csv`}>
            Download reconciliation (CSV)
          </a>
        </Button>
        {r.held > 0 && (
          <Button asChild size="sm" variant="outline">
            <a href={`/api/v1/imports/batches/${id}/errors`}>
              Download error report (CSV)
            </a>
          </Button>
        )}
        {r.quarantined > 0 && (
          <Button asChild size="sm" variant="outline">
            <Link to="/duplicates">Review possible duplicates</Link>
          </Button>
        )}
      </div>
    </section>
  );
}

export function ImportBatchPage() {
  const { id = '' } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [reviewed, setReviewed] = useState(false);
  const [reason, setReason] = useState('');

  const batch = useQuery({
    queryKey: ['import-batch', id],
    queryFn: () => api<Batch>(`/imports/batches/${id}`),
    refetchInterval: (q) =>
      q.state.data?.status === 'committing' ? 2000 : false,
  });

  const act = useMutation({
    mutationFn: ({ verb, body }: { verb: string; body?: unknown }) =>
      post<Batch>(`/imports/batches/${id}/${verb}`, body),
    onSuccess: (_d, { verb }) => {
      qc.invalidateQueries({ queryKey: ['import-batch', id] });
      qc.invalidateQueries({ queryKey: ['import-rows', id] });
      qc.invalidateQueries({ queryKey: ['import-reconciliation', id] });
      qc.invalidateQueries({ queryKey: ['import-batches'] });
      toast.success(
        {
          approve: 'Approved. You can load it now.',
          commit: 'Loaded.',
          rollback: 'Rolled back.',
          cancel: 'Cancelled.',
        }[verb] ?? 'Done.',
      );
      setReason('');
    },
  });

  const canCommit = can('imports.commit');
  const b = batch.data;
  const status = b?.status ?? '';
  const loaded = status === 'committed' || status === 'partially_committed';
  const step =
    status === 'validated'
      ? reviewed
        ? 4
        : 3
      : status === 'approved' || status === 'committing'
        ? 5
        : loaded || status === 'rolled_back'
          ? 6
          : 3;
  const c = b?.counts ?? {};
  const loadable = (c.create ?? 0) + (c.update ?? 0);

  return (
    <>
      <Helmet>
        <title>Import - PI 360</title>
      </Helmet>
      <div className="container-fluid space-y-5">
        <Toolbar>
          <ToolbarHeading>
            <ToolbarPageTitle text={b ? b.file_name : 'Import'} />
          </ToolbarHeading>
          <Button asChild variant="outline" size="sm">
            <Link to="/imports">All imports</Link>
          </Button>
        </Toolbar>

        {batch.isPending && <LoadingState />}
        {batch.isError && (
          <ErrorState error={batch.error} onRetry={() => batch.refetch()} />
        )}

        {b && (
          <>
            <ImportStepper current={step} />
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <StatusBadge status={b.status} />
              <span className="text-muted-foreground">
                Mapping: {b.template} - uploaded{' '}
                {new Date(b.created_at).toLocaleString()}
              </span>
            </div>
            {act.error && (
              <Notice tone="error" title="This could not be done">
                {errorText(act.error)}
              </Notice>
            )}
            {b.duplicate_of && (
              <Notice tone="warning" title="This exact file was loaded before">
                Rows already loaded are skipped, so nothing is created twice.
              </Notice>
            )}

            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              <Count label="Rows in file" value={c.total} hint="data rows" />
              <Count label="Will create" value={c.create} hint="new people" />
              <Count
                label="Will update"
                value={c.update}
                hint="matched records"
              />
              <Count label="Blocked" value={c.held} hint="fixed in the file" />
              <Count label="Skipped" value={c.skip} hint="already loaded" />
            </div>
            {(c.warnings ?? 0) > 0 && (
              <p className="text-sm text-muted-foreground">
                {c.warnings} rows carry warnings. They still load; check the
                reasons below.
              </p>
            )}

            {status === 'validated' && step === 3 && (
              <>
                <h2 className="font-medium">Review the rows</h2>
                <RowsTable id={id} loaded={false} />
                <div className="flex gap-2">
                  <Button onClick={() => setReviewed(true)}>
                    Continue to approval
                  </Button>
                  <Button
                    variant="outline"
                    disabled={act.isPending}
                    onClick={() => act.mutate({ verb: 'cancel' })}
                  >
                    Cancel this import
                  </Button>
                </div>
              </>
            )}

            {status === 'validated' && step === 4 && (
              <section className="rounded-lg border p-4 space-y-3 max-w-2xl">
                <h2 className="font-medium">Approve for loading</h2>
                <p className="text-sm">
                  Approving will create {c.create ?? 0} and update{' '}
                  {c.update ?? 0} records. {c.held ?? 0} blocked rows will not
                  load; they stay in the error report for the file&apos;s owner
                  to fix and re-send. Possible duplicates found afterwards go to
                  a steward, never merged automatically.
                </p>
                {!canCommit ? (
                  <Notice title="Approval needs another role">
                    You can validate and review. Someone with approval rights
                    must approve it.
                  </Notice>
                ) : loadable === 0 ? (
                  <Notice tone="warning" title="Nothing to load">
                    Every row is blocked or already loaded. Fix the file and
                    import it again.
                  </Notice>
                ) : (
                  <Button
                    disabled={act.isPending}
                    onClick={() => act.mutate({ verb: 'approve' })}
                  >
                    Approve
                  </Button>
                )}
                <Button variant="outline" onClick={() => setReviewed(false)}>
                  Back to review
                </Button>
              </section>
            )}

            {(status === 'approved' || status === 'committing') && (
              <section className="rounded-lg border p-4 space-y-3 max-w-2xl">
                <h2 className="font-medium">Load into PI 360</h2>
                <p className="text-sm text-muted-foreground">
                  Rows load in chunks. If it stops part-way, the rows already
                  loaded stay and loading again continues without creating
                  anything twice.
                </p>
                {status === 'committing' ? (
                  <p className="text-sm" role="status">
                    Loading... this page refreshes by itself.
                  </p>
                ) : canCommit ? (
                  <Button
                    disabled={act.isPending}
                    onClick={() => act.mutate({ verb: 'commit' })}
                  >
                    {act.isPending ? 'Loading...' : 'Load now'}
                  </Button>
                ) : (
                  <Notice title="Loading needs another role" />
                )}
              </section>
            )}

            {(loaded || status === 'rolled_back') && (
              <>
                <ReconciliationPanel id={id} />
                {loaded && canCommit && (
                  <section className="rounded-lg border p-4 space-y-2 max-w-2xl">
                    <h2 className="font-medium">Roll back this import</h2>
                    <p className="text-sm text-muted-foreground">
                      Reverts what this file created or changed. It is refused
                      if people from this file have since been merged.
                    </p>
                    <Input
                      placeholder="Reason (required)"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                    <Button
                      variant="destructive"
                      disabled={!reason.trim() || act.isPending}
                      onClick={() =>
                        act.mutate({ verb: 'rollback', body: { reason } })
                      }
                    >
                      Roll back
                    </Button>
                  </section>
                )}
                <RowsTable id={id} loaded={loaded} />
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
