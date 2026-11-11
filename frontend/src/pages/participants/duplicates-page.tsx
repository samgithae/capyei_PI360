import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
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
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

interface Person {
  id: string;
  name: string;
  gender: string;
  age: number | null;
  date_of_birth: string | null;
  status: string;
  county: string;
  programmes: string[];
  cohorts: string[];
  enrollment_numbers: string[];
  phones?: string[];
}
interface Candidate {
  id: string;
  score: number;
  reasons: { code: string; text: string }[];
  status: string;
  note: string;
  a: Person;
  b: Person;
}
interface MergeRow {
  id: string;
  survivor: { id: string; name: string };
  absorbed: { id: string; name: string };
  reason: string;
  created_at: string;
  created_by: string;
  undone_at: string | null;
  undo_reason: string;
}

// [label, value of a person, field the merge API can take from the other record]
const ROWS: [string, (p: Person) => string, string?][] = [
  ['Name', (p) => p.name, 'full_name_source'],
  ['Gender', (p) => p.gender, 'gender'],
  ['Age', (p) => String(p.age ?? ''), 'age_at_source'],
  ['Date of birth', (p) => p.date_of_birth ?? '', 'date_of_birth'],
  ['County', (p) => p.county, 'origin_county_id'],
  ['Status', (p) => p.status, 'status'],
  ['Programmes', (p) => p.programmes.join(', ')],
  ['Cohorts', (p) => p.cohorts.join(', ')],
  ['Enrollment no.', (p) => p.enrollment_numbers.join(', ')],
  ['Phone', (p) => (p.phones ?? []).join(', ')],
];

function errorText(e: unknown) {
  return e instanceof ApiError ? e.message : 'Something went wrong.';
}

function CandidateCard({
  c,
  canMerge,
  onDone,
}: {
  c: Candidate;
  canMerge: boolean;
  onDone: () => void;
}) {
  const [survivor, setSurvivor] = useState<'a' | 'b'>('a');
  const [take, setTake] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState('');
  const other = survivor === 'a' ? c.b : c.a;
  const merge = useMutation({
    mutationFn: () =>
      post(`/participants/duplicates/${c.id}/merge`, {
        survivor: c[survivor].id,
        fields: Object.fromEntries([...take].map((f) => [f, 'merged'])),
        reason,
      }),
    onSuccess: onDone,
  });
  const dismiss = useMutation({
    mutationFn: () =>
      post(`/participants/duplicates/${c.id}/dismiss`, { reason }),
    onSuccess: onDone,
  });
  const error = merge.error ?? dismiss.error;

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{Math.round(c.score * 100)}% likely</Badge>
          {c.reasons.map((r) => (
            <Badge key={r.code} variant="secondary">
              {r.text}
            </Badge>
          ))}
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead></TableHead>
              {(['a', 'b'] as const).map((k) => (
                <TableHead key={k}>
                  {canMerge ? (
                    <label className="flex items-center gap-2">
                      <input
                        type="radio"
                        name={`survivor-${c.id}`}
                        checked={survivor === k}
                        onChange={() => {
                          setSurvivor(k);
                          setTake(new Set());
                        }}
                      />
                      Keep this record
                    </label>
                  ) : (
                    `Record ${k.toUpperCase()}`
                  )}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROWS.map(([label, get, field]) => {
              const va = get(c.a);
              const vb = get(c.b);
              if (!va && !vb) return null;
              const differs = va !== vb;
              return (
                <TableRow key={label}>
                  <TableCell>{label}</TableCell>
                  <TableCell>{va || '-'}</TableCell>
                  <TableCell>
                    {vb || '-'}
                    {canMerge && differs && field && (
                      <label className="ml-3 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          className="mr-1"
                          checked={take.has(field)}
                          onChange={(e) => {
                            const next = new Set(take);
                            if (e.target.checked) next.add(field);
                            else next.delete(field);
                            setTake(next);
                          }}
                        />
                        {/* the checkbox always refers to the record that is NOT kept */}
                        use {survivor === 'a' ? 'B' : 'A'}'s value
                      </label>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        {canMerge ? (
          <div className="flex flex-wrap items-center gap-2">
            <Input
              aria-label="Reason"
              placeholder={`Reason (kept: ${c[survivor].name}, merged in: ${other.name})`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="max-w-md"
            />
            <Button
              disabled={!reason.trim() || merge.isPending}
              onClick={() => merge.mutate()}
            >
              Merge
            </Button>
            <Button
              variant="outline"
              disabled={!reason.trim() || dismiss.isPending}
              onClick={() => dismiss.mutate()}
            >
              Not the same person
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            You can review this pair; merging needs the merge permission.
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {errorText(error)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function History({ canMerge }: { canMerge: boolean }) {
  const qc = useQueryClient();
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const merges = useQuery({
    queryKey: ['merges'],
    queryFn: () => api<{ results: MergeRow[] }>('/participants/merges'),
  });
  const undo = useMutation({
    mutationFn: (id: string) =>
      post(`/participants/merges/${id}/undo`, { reason: reasons[id] ?? '' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['merges'] });
      qc.invalidateQueries({ queryKey: ['duplicates'] });
    },
  });
  const rows = merges.data?.results ?? [];
  return (
    <div className="space-y-2">
      {merges.isError && (
        <ErrorState error={merges.error} onRetry={() => merges.refetch()} />
      )}
      {merges.isPending && <LoadingState />}
      {merges.data && rows.length === 0 && <EmptyState title="No merges yet" />}
      {rows.map((m) => (
        <div key={m.id} className="rounded-lg border p-3 text-sm space-y-2">
          <div>
            <strong>{m.absorbed.name}</strong> merged into{' '}
            <strong>{m.survivor.name}</strong> by {m.created_by} on{' '}
            {m.created_at.slice(0, 10)}. Reason: {m.reason}
          </div>
          {m.undone_at ? (
            <Badge variant="secondary">
              Undone {m.undone_at.slice(0, 10)}: {m.undo_reason}
            </Badge>
          ) : (
            canMerge && (
              <div className="flex gap-2">
                <Input
                  aria-label="Undo reason"
                  placeholder="Reason for undoing"
                  className="max-w-sm"
                  value={reasons[m.id] ?? ''}
                  onChange={(e) =>
                    setReasons({ ...reasons, [m.id]: e.target.value })
                  }
                />
                <Button
                  variant="outline"
                  disabled={!(reasons[m.id] ?? '').trim() || undo.isPending}
                  onClick={() => undo.mutate(m.id)}
                >
                  Undo merge
                </Button>
              </div>
            )
          )}
        </div>
      ))}
      {undo.isError && (
        <p role="alert" className="text-sm text-destructive">
          {errorText(undo.error)}
        </p>
      )}
    </div>
  );
}

export function DuplicatesPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<'open' | 'dismissed' | 'history'>('open');
  const queue = useQuery({
    queryKey: ['duplicates', tab],
    queryFn: () =>
      api<{ results: Candidate[] }>(`/participants/duplicates?status=${tab}`),
    enabled: tab !== 'history',
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['duplicates'] });
    qc.invalidateQueries({ queryKey: ['merges'] });
  };
  const scan = useMutation({
    mutationFn: () =>
      post<{ pairs: number; new: number }>('/participants/duplicates/scan'),
    onSuccess: refresh,
  });
  const canMerge = can('duplicates.merge');

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Duplicates | PI 360</title>
      </Helmet>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>Possible duplicates</ToolbarPageTitle>
        </ToolbarHeading>
        <Button variant="outline" onClick={() => scan.mutate()}>
          Scan for duplicates
        </Button>
      </Toolbar>
      <p className="text-sm text-muted-foreground">
        Nothing here merges on its own. You decide, and every merge can be
        undone. The matching rules are proposals until the data-readiness audit
        confirms them.
      </p>
      {scan.data && (
        <p role="status" className="text-sm">
          Scan finished: {scan.data.new} new pair(s), {scan.data.pairs} in
          total.
        </p>
      )}
      <div className="flex gap-2">
        {(
          [
            ['open', 'To review'],
            ['dismissed', 'Dismissed'],
            ['history', 'Merge history'],
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
      {tab === 'history' ? (
        <History canMerge={canMerge} />
      ) : (
        <div className="space-y-4">
          {queue.isError && (
            <ErrorState error={queue.error} onRetry={() => queue.refetch()} />
          )}
          {queue.isPending && <LoadingState />}
          {queue.data?.results.length === 0 && (
            <EmptyState
              title={tab === 'open' ? 'Nothing to review' : 'Nothing dismissed'}
            />
          )}
          {queue.data?.results.map((c) => (
            <CandidateCard
              key={c.id}
              c={c}
              canMerge={canMerge && tab === 'open'}
              onDone={refresh}
            />
          ))}
        </div>
      )}
    </div>
  );
}
