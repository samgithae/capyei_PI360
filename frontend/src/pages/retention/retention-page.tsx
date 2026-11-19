import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { errorText, Required } from '@/pages/cases/case-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { toast } from 'sonner';
import { api, post } from '@/lib/api';
import { formatDateTime } from '@/lib/helpers';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Section } from '@/components/shared/info-card';
import { ConfirmDialog, FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { ErrorState, LoadingState } from '@/components/states';

export type RetentionClass = {
  code: string;
  label: string;
  description: string;
  removes: string;
  keeps: string;
  minimum_days: number;
  period_days: number | null;
  basis: string;
  state: 'not_set' | 'awaiting_approval' | 'active';
  approved_by: string;
  approved_at: string | null;
};

export type RetentionRun = {
  id: string;
  applied: boolean;
  by: string;
  at: string;
  results: Record<string, Record<string, unknown>>;
};

type Overview = { classes: RetentionClass[]; runs: RetentionRun[] };

const STATE: Record<
  RetentionClass['state'],
  { label: string; variant: 'secondary' | 'warning' | 'success' }
> = {
  not_set: { label: 'No period set', variant: 'secondary' },
  awaiting_approval: { label: 'Waiting for approval', variant: 'warning' },
  active: { label: 'Active', variant: 'success' },
};

/** "rows: 3, batches: 1" for a result entry; plain text for a skip reason. */
function describe(entry: Record<string, unknown>) {
  return Object.entries(entry)
    .map(([k, v]) =>
      typeof v === 'object' && v !== null
        ? `${k}: ${Object.entries(v as Record<string, unknown>)
            .map(([a, b]) => `${b} ${a}`)
            .join(', ')}`
        : `${k}: ${String(v)}`,
    )
    .join(' · ');
}

function PeriodDialog({
  item,
  onOpenChange,
}: {
  item: RetentionClass;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [days, setDays] = useState(String(item.period_days ?? ''));
  const [basis, setBasis] = useState(item.basis);
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () =>
      api(`/retention/${item.code}`, {
        method: 'PUT',
        body: JSON.stringify({
          period_days: Number(days),
          basis: basis.trim(),
        }),
      }),
    onSuccess: () => {
      toast.success('Period saved. It needs approval before it is used.');
      void qc.invalidateQueries({ queryKey: ['retention'] });
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open
      onOpenChange={onOpenChange}
      title={`Retention period: ${item.label}`}
      description="Changing the period withdraws any earlier approval. Nothing is reduced until someone approves the new period."
      submitLabel="Save period"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        const n = Number(days);
        if (!Number.isInteger(n) || n < item.minimum_days)
          return setError(
            `Give a whole number of days, at least ${item.minimum_days}.`,
          );
        if (!basis.trim()) return setError('Say why this period was chosen.');
        setError('');
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="ret-days">
          Keep the values for this many days after sign-off
          <Required />
        </Label>
        <Input
          id="ret-days"
          type="number"
          value={days}
          onChange={(e) => setDays(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="ret-basis">
          Basis (policy, agreement or decision)
          <Required />
        </Label>
        <Textarea
          id="ret-basis"
          maxLength={2000}
          value={basis}
          onChange={(e) => setBasis(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

function RevokeDialog({
  item,
  onOpenChange,
}: {
  item: RetentionClass;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const revoke = useMutation({
    mutationFn: () => post(`/retention/${item.code}/revoke`, { reason }),
    onSuccess: () => {
      toast.success('Approval withdrawn. The job will skip this class.');
      void qc.invalidateQueries({ queryKey: ['retention'] });
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open
      onOpenChange={onOpenChange}
      title={`Withdraw approval: ${item.label}`}
      submitLabel="Withdraw approval"
      pending={revoke.isPending}
      error={error}
      onSubmit={() => {
        if (!reason.trim()) return setError('Give a reason.');
        setError('');
        revoke.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="ret-reason">
          Reason
          <Required />
        </Label>
        <Input
          id="ret-reason"
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

/** Administration: how long each class of data is kept before its personal values are cleared.
 * A class is only reduced when it has a period and that period has been approved (T-073). */
export function RetentionPage() {
  const { can } = useAuth();
  const canManage = can('retention.manage');
  const qc = useQueryClient();
  const [period, setPeriod] = useState<RetentionClass | null>(null);
  const [revoking, setRevoking] = useState<RetentionClass | null>(null);
  const [applying, setApplying] = useState(false);
  const q = useQuery({
    queryKey: ['retention'],
    queryFn: () => api<Overview>('/retention'),
  });
  const done = () => void qc.invalidateQueries({ queryKey: ['retention'] });
  const approve = useMutation({
    mutationFn: (code: string) => post(`/retention/${code}/approve`),
    onSuccess: () => {
      toast.success('Approved. The next applied run will use this period.');
      done();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const run = useMutation({
    mutationFn: (apply: boolean) =>
      post<RetentionRun>('/retention/run', { apply, confirm: apply }),
    onSuccess: (r) => {
      toast.success(
        r.applied ? 'Run applied.' : 'Dry run finished. Nothing changed.',
      );
      done();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const classes = q.data?.classes ?? [];
  const ready = classes.some((c) => c.state === 'active');

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Data retention | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Administration', to: '/administration' },
          { label: 'Data retention' },
        ]}
        title="Data retention"
        description="How long personal values are kept before they are cleared. Nothing is cleared unless a class has a period and that period has been approved. A dry run shows what would be cleared without changing anything."
        actions={
          canManage ? (
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={run.isPending}
                onClick={() => run.mutate(false)}
              >
                Dry run
              </Button>
              <Button
                variant="destructive"
                disabled={run.isPending || !ready}
                onClick={() => setApplying(true)}
              >
                Apply now
              </Button>
            </div>
          ) : undefined
        }
      />
      {q.isError && (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      )}
      {q.isPending && <LoadingState />}
      {classes.map((c) => (
        <Section
          key={c.code}
          title={c.label}
          action={
            <Badge variant={STATE[c.state].variant} appearance="light">
              {STATE[c.state].label}
            </Badge>
          }
        >
          <div className="space-y-3 text-sm">
            <p>{c.description}</p>
            <p>
              <span className="font-medium">Clears: </span>
              {c.removes}
            </p>
            <p>
              <span className="font-medium">Keeps: </span>
              {c.keeps}
            </p>
            <p>
              <span className="font-medium">Period: </span>
              {c.period_days === null
                ? `Not set (minimum ${c.minimum_days} days)`
                : `${c.period_days} days after sign-off`}
            </p>
            {c.basis && (
              <p>
                <span className="font-medium">Basis: </span>
                {c.basis}
              </p>
            )}
            {c.approved_at && (
              <p className="text-muted-foreground">
                Approved by {c.approved_by || 'a user'} on{' '}
                {formatDateTime(c.approved_at)}
              </p>
            )}
            {canManage && (
              <div className="flex flex-wrap gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPeriod(c)}
                >
                  {c.period_days === null ? 'Set period' : 'Change period'}
                </Button>
                {c.state === 'awaiting_approval' && (
                  <Button
                    size="sm"
                    disabled={approve.isPending}
                    onClick={() => approve.mutate(c.code)}
                  >
                    Approve
                  </Button>
                )}
                {c.state === 'active' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setRevoking(c)}
                  >
                    Withdraw approval
                  </Button>
                )}
              </div>
            )}
          </div>
        </Section>
      ))}
      {q.data && (
        <Section title="Recent runs">
          {q.data.runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {q.data.runs.map((r) => (
                <li key={r.id}>
                  <span className="font-medium">
                    {r.applied ? 'Applied' : 'Dry run'}
                  </span>{' '}
                  · {formatDateTime(r.at)} · {r.by}
                  {Object.entries(r.results).map(([code, entry]) => (
                    <p key={code} className="text-muted-foreground">
                      {code}: {describe(entry)}
                    </p>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}
      {period && (
        <PeriodDialog
          key={period.code}
          item={period}
          onOpenChange={(o) => !o && setPeriod(null)}
        />
      )}
      {revoking && (
        <RevokeDialog
          key={revoking.code}
          item={revoking}
          onOpenChange={(o) => !o && setRevoking(null)}
        />
      )}
      <ConfirmDialog
        open={applying}
        onOpenChange={setApplying}
        title="Clear personal values now?"
        description="This permanently clears the values of every approved class that is past its period. It cannot be undone. Run a dry run first to see the counts."
        confirmLabel="Clear values"
        onConfirm={() => run.mutate(true)}
      />
    </div>
  );
}
