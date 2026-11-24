import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ExportButton } from '@/components/shared/export-button';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

interface RuleCount {
  code: string;
  label: string;
  fix: string;
  count: number;
}
interface Summary {
  checked: number;
  failing: number;
  rules: RuleCount[];
}
interface QualityRecord {
  id: string;
  name: string;
  county: string;
  projects: string[];
  enrollment_numbers: string[];
  issues: { code: string; label: string; fix: string }[];
}
interface Records {
  total: number;
  page_size: number;
  results: QualityRecord[];
}
interface Correction {
  id: string;
  participant: { id: string; name: string };
  field_label: string;
  was: string;
  now: string;
  state: string;
  state_label: string;
  enrollment_no: string;
  project: string;
  corrected_by: string;
  corrected_at: string;
  conflict: { value: string; batch: string; at: string } | null;
  closed_how: string;
  closed_note: string;
}
interface Corrections {
  total: number;
  page_size: number;
  counts: { open: number; conflict: number };
  results: Correction[];
}

const STATES = [
  ['open', 'To tell the MIS'],
  ['conflict', 'Import disagreed'],
  ['confirmed', 'Done in MIS'],
  ['closed', 'Closed'],
  ['all', 'All'],
] as const;

function errorText(e: unknown) {
  return e instanceof ApiError ? e.message : 'Something went wrong.';
}

function Pager({
  offset,
  size,
  total,
  onChange,
}: {
  offset: number;
  size: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  if (total <= size) return null;
  return (
    <div className="flex items-center gap-2 text-sm">
      <Button
        variant="outline"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(offset - size, 0))}
      >
        Previous
      </Button>
      <span>
        {offset + 1} to {Math.min(offset + size, total)} of {total}
      </span>
      <Button
        variant="outline"
        disabled={offset + size >= total}
        onClick={() => onChange(offset + size)}
      >
        Next
      </Button>
    </div>
  );
}

function RecordsToFix() {
  const [rule, setRule] = useState('');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const summary = useQuery({
    queryKey: ['dq-summary'],
    queryFn: () => api<Summary>('/participants/data-quality'),
  });
  const params = new URLSearchParams({ offset: String(offset) });
  if (rule) params.set('rule', rule);
  if (q.trim()) params.set('q', q.trim());
  const records = useQuery({
    queryKey: ['dq-records', params.toString()],
    queryFn: () => api<Records>(`/participants/data-quality/records?${params}`),
  });

  return (
    <div className="space-y-4">
      {summary.isError && (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
      )}
      {summary.data && (
        <>
          <p className="text-sm text-muted-foreground">
            {summary.data.failing} of {summary.data.checked} youth have at least
            one problem. Choose a rule to list only those youth.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {summary.data.rules.map((r) => (
              <button
                key={r.code}
                type="button"
                aria-pressed={rule === r.code}
                onClick={() => {
                  setRule(rule === r.code ? '' : r.code);
                  setOffset(0);
                }}
                className={`rounded-lg border p-3 text-left text-sm ${
                  rule === r.code ? 'border-primary bg-primary/5' : ''
                }`}
              >
                <div className="text-2xl font-semibold">{r.count}</div>
                <div className="font-medium">{r.label}</div>
                <div className="text-muted-foreground">{r.fix}</div>
              </button>
            ))}
          </div>
        </>
      )}
      <Input
        aria-label="Search by name"
        placeholder="Search by name"
        className="max-w-sm"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOffset(0);
        }}
      />
      {records.isError && (
        <ErrorState error={records.error} onRetry={() => records.refetch()} />
      )}
      {records.isPending && <LoadingState />}
      {records.data?.results.length === 0 && (
        <EmptyState title="No youth fail these checks" />
      )}
      {!!records.data?.results.length && (
        <Card>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Youth</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>County</TableHead>
                  <TableHead>What to fix</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.data.results.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>
                      <Link
                        to={`/youth/${r.id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {r.name}
                      </Link>
                    </TableCell>
                    <TableCell>{r.projects.join(', ') || '-'}</TableCell>
                    <TableCell>{r.county || '-'}</TableCell>
                    <TableCell className="space-x-1">
                      {r.issues.map((i) => (
                        <Badge key={i.code} variant="secondary" title={i.fix}>
                          {i.label}
                        </Badge>
                      ))}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
      {records.data && (
        <Pager
          offset={offset}
          size={records.data.page_size}
          total={records.data.total}
          onChange={setOffset}
        />
      )}
    </div>
  );
}

function CorrectionRow({ c, onDone }: { c: Correction; onDone: () => void }) {
  const [note, setNote] = useState('');
  const resolve = useMutation({
    mutationFn: (action: 'confirm' | 'keep' | 'accept') =>
      post(`/participants/corrections/${c.id}/resolve`, { action, note }),
    onSuccess: onDone,
  });
  const open = c.state === 'open';
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/youth/${c.participant.id}`}
            className="font-medium text-primary hover:underline"
          >
            {c.participant.name}
          </Link>
          {c.enrollment_no && (
            <span className="text-sm text-muted-foreground">
              {c.project} {c.enrollment_no}
            </span>
          )}
          <Badge variant="secondary">{c.state_label}</Badge>
          {c.conflict && <Badge variant="destructive">Import disagreed</Badge>}
        </div>
        <div className="text-sm">
          <strong>{c.field_label}</strong>: MIS has{' '}
          <span className="font-mono">{c.was || '(empty)'}</span>, corrected to{' '}
          <span className="font-mono">{c.now || '(empty)'}</span> by{' '}
          {c.corrected_by} on {c.corrected_at.slice(0, 10)}.
        </div>
        {c.conflict && (
          <p role="alert" className="text-sm text-destructive">
            A later import ({c.conflict.batch || 'unnamed batch'}) carried{' '}
            <span className="font-mono">{c.conflict.value || '(empty)'}</span>{' '}
            and was held back. Keep the correction, or accept the MIS value.
          </p>
        )}
        {!open && c.closed_note && (
          <p className="text-sm text-muted-foreground">Note: {c.closed_note}</p>
        )}
        {open && (
          <div className="flex flex-wrap items-center gap-2">
            <Input
              aria-label={`Note for ${c.participant.name}`}
              placeholder="Note (optional)"
              className="max-w-xs"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <Button
              disabled={resolve.isPending}
              onClick={() => resolve.mutate('confirm')}
            >
              MIS updated
            </Button>
            {c.conflict && (
              <>
                <Button
                  variant="outline"
                  disabled={resolve.isPending}
                  onClick={() => resolve.mutate('keep')}
                >
                  Keep my fix
                </Button>
                <Button
                  variant="outline"
                  disabled={resolve.isPending}
                  onClick={() => resolve.mutate('accept')}
                >
                  Accept MIS value
                </Button>
              </>
            )}
          </div>
        )}
        {resolve.isError && (
          <p role="alert" className="text-sm text-destructive">
            {errorText(resolve.error)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function MisCorrections() {
  const qc = useQueryClient();
  const [state, setState] = useState<(typeof STATES)[number][0]>('open');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({ state });
  if (q.trim()) params.set('q', q.trim());
  const list = useQuery({
    queryKey: ['dq-corrections', params.toString(), offset],
    queryFn: () =>
      api<Corrections>(`/participants/corrections?${params}&offset=${offset}`),
  });

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        When staff fix a name, gender, age, county or enrolment status that came
        from the MIS, the fix is listed here for whoever updates the MIS. A
        later import will not overwrite it without your review.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {STATES.map(([k, label]) => (
          <Button
            key={k}
            variant={state === k ? 'primary' : 'outline'}
            onClick={() => {
              setState(k);
              setOffset(0);
            }}
          >
            {label}
            {list.data && k === 'open' && ` (${list.data.counts.open})`}
            {list.data && k === 'conflict' && ` (${list.data.counts.conflict})`}
          </Button>
        ))}
        <ExportButton
          table="corrections"
          params={params}
          noun="corrections"
          total={list.data?.total}
        />
      </div>
      <Input
        aria-label="Search corrections by name"
        placeholder="Search by name"
        className="max-w-sm"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOffset(0);
        }}
      />
      {list.isError && (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      )}
      {list.isPending && <LoadingState />}
      {list.data?.results.length === 0 && (
        <EmptyState title="No corrections here" />
      )}
      {list.data?.results.map((c) => (
        <CorrectionRow
          key={c.id}
          c={c}
          onDone={() => qc.invalidateQueries({ queryKey: ['dq-corrections'] })}
        />
      ))}
      {list.data && (
        <Pager
          offset={offset}
          size={list.data.page_size}
          total={list.data.total}
          onChange={setOffset}
        />
      )}
    </div>
  );
}

export function DataQualityPage() {
  const [tab, setTab] = useState<'records' | 'corrections'>('records');
  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Data quality | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Data quality' }]}
        title="Data quality"
        description="Records that fail the checks, and the corrections staff have made to MIS data."
      />
      <div className="flex gap-2">
        {(
          [
            ['records', 'Records to fix'],
            ['corrections', 'MIS corrections'],
          ] as const
        ).map(([k, label]) => (
          <Button
            key={k}
            variant={tab === k ? 'primary' : 'outline'}
            onClick={() => setTab(k)}
          >
            {label}
          </Button>
        ))}
      </div>
      {tab === 'records' ? <RecordsToFix /> : <MisCorrections />}
    </div>
  );
}
