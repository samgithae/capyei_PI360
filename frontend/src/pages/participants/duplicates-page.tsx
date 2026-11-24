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
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import {
  CriticalList,
  PlacementResolver,
  ResolutionList,
  unchosen,
  type Keep,
  type Resolution,
  type Review,
} from './merge-conflicts';

interface Person {
  id: string;
  name: string;
  gender: string;
  age: number | null;
  date_of_birth: string | null;
  status: string;
  county: string;
  projects: string[];
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
  pending?: {
    survivor: string;
    reason: string;
    saved_at: string;
    resolutions: Resolution[];
  };
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
  ['Projects', (p) => p.projects.join(', ')],
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
  const [choices, setChoices] = useState<Record<string, Keep>>({});
  const [reason, setReason] = useState('');
  const other = survivor === 'a' ? c.b : c.a;
  // What the server would do with this survivor: gaps filled, conflicts to choose, holds.
  const review = useQuery({
    queryKey: ['duplicate-review', c.id, c[survivor].id],
    queryFn: () =>
      api<Review>(
        `/participants/duplicates/${c.id}/review?survivor=${c[survivor].id}`,
      ),
    enabled: canMerge,
  });
  const byField = Object.fromEntries(
    (review.data?.fields ?? []).map((f) => [f.field, f]),
  );
  const open = unchosen(review.data?.fields ?? [], choices);
  const critical = review.data?.critical ?? [];
  const merge = useMutation({
    mutationFn: () =>
      post(`/participants/duplicates/${c.id}/merge`, {
        survivor: c[survivor].id,
        fields: choices,
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
                          setChoices({});
                        }}
                      />
                      Keep record {k.toUpperCase()}
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
              return (
                <TableRow key={label}>
                  <TableCell>{label}</TableCell>
                  <TableCell>{va || '-'}</TableCell>
                  <TableCell>
                    {vb || '-'}
                    {canMerge && field && byField[field] && (
                      <FieldChoice
                        name={`${c.id}-${field}`}
                        f={byField[field]}
                        choice={choices[field]}
                        otherLetter={survivor === 'a' ? 'B' : 'A'}
                        onChoose={(k) => setChoices({ ...choices, [field]: k })}
                      />
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        {canMerge && <CriticalList conflicts={critical} />}
        {canMerge && open.length > 0 && (
          <p className="text-sm">
            Choose which value to keep for: {open.join(', ')}.
          </p>
        )}
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
              disabled={
                !reason.trim() ||
                merge.isPending ||
                !review.data ||
                open.length > 0
              }
              onClick={() => merge.mutate()}
            >
              {critical.length ? 'Save merge, pending resolution' : 'Merge'}
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

function FieldChoice({
  name,
  f,
  choice,
  otherLetter,
  onChoose,
}: {
  name: string;
  f: Review['fields'][number];
  choice?: Keep;
  otherLetter: string;
  onChoose: (k: Keep) => void;
}) {
  if (!f.conflict) {
    return f.keep === 'merged' ? (
      <span className="ml-3 text-xs text-muted-foreground">
        fills the gap on the kept record
      </span>
    ) : null;
  }
  // A real difference: never guessed, the steward picks one side.
  return (
    <span className="ml-3 inline-flex gap-3 text-xs">
      {(
        [
          ['survivor', `keep ${otherLetter === 'A' ? 'B' : 'A'}'s value`],
          ['merged', `use ${otherLetter}'s value`],
        ] as const
      ).map(([k, label]) => (
        <label key={k} className="flex items-center gap-1">
          <input
            type="radio"
            name={name}
            checked={choice === k}
            onChange={() => onChoose(k)}
          />
          {label}
        </label>
      ))}
    </span>
  );
}

/** A merge saved as pending resolution: show what holds it, let an authorised officer resolve
 * the placement conflict, then complete. Other conflicts are fixed where the hint says. */
function PendingCard({
  c,
  canMerge,
  canEditPlacements,
  onDone,
}: {
  c: Candidate;
  canMerge: boolean;
  canEditPlacements: boolean;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const survivorId = c.pending?.survivor ?? c.a.id;
  const kept = survivorId === c.a.id ? c.a : c.b;
  const merged = survivorId === c.a.id ? c.b : c.a;
  const review = useQuery({
    queryKey: ['duplicate-review', c.id, survivorId],
    queryFn: () =>
      api<Review>(
        `/participants/duplicates/${c.id}/review?survivor=${survivorId}`,
      ),
    enabled: canMerge,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['duplicate-review', c.id] });
    onDone();
  };
  const complete = useMutation({
    mutationFn: () => post(`/participants/duplicates/${c.id}/complete`),
    onSuccess: refresh,
  });
  const dismiss = useMutation({
    mutationFn: () =>
      post(`/participants/duplicates/${c.id}/dismiss`, { reason: note }),
    onSuccess: refresh,
  });
  const critical = review.data?.critical ?? [];
  const placements = critical.find((x) => x.code === 'two_running_placements');
  const error = complete.error ?? dismiss.error;
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="warning">Pending resolution</Badge>
          <span className="text-sm">
            Keep <strong>{kept.name}</strong>, merge in{' '}
            <strong>{merged.name}</strong>. Saved{' '}
            {c.pending?.saved_at?.slice(0, 10)}. Reason: {c.pending?.reason}
          </span>
        </div>
        <ResolutionList rows={c.pending?.resolutions ?? []} />
        {review.isPending && canMerge && <LoadingState />}
        <CriticalList conflicts={critical} />
        {canMerge && placements && (
          <PlacementResolver
            candidateId={c.id}
            conflict={placements}
            canEditPlacements={canEditPlacements}
            onDone={refresh}
          />
        )}
        {canMerge && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={
                !review.data || critical.length > 0 || complete.isPending
              }
              onClick={() => complete.mutate()}
            >
              Complete merge
            </Button>
            <Input
              aria-label="Reason"
              placeholder="Reason, if they are not the same person"
              className="max-w-sm"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <Button
              variant="outline"
              disabled={!note.trim() || dismiss.isPending}
              onClick={() => dismiss.mutate()}
            >
              Not the same person
            </Button>
          </div>
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
  const [tab, setTab] = useState<'open' | 'pending' | 'dismissed' | 'history'>(
    'open',
  );
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
      <PageHeader
        crumbs={[{ label: 'Possible duplicates' }]}
        title="Possible duplicates"
        actions={
          <>
            <Button variant="outline" onClick={() => scan.mutate()}>
              Scan for duplicates
            </Button>
          </>
        }
      />
      <p className="text-sm text-muted-foreground">
        Nothing here merges on its own. You decide, and every merge can be
        undone. Where both records hold something only one youth can have (two
        running placements, say), the merge waits under Waiting on conflicts
        until it is resolved. The matching rules are proposals until the
        data-readiness audit confirms them.
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
            ['pending', 'Waiting on conflicts'],
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
              title={
                tab === 'open'
                  ? 'Nothing to review'
                  : tab === 'pending'
                    ? 'No merge is waiting'
                    : 'Nothing dismissed'
              }
            />
          )}
          {queue.data?.results.map((c) =>
            c.status === 'pending' ? (
              <PendingCard
                key={c.id}
                c={c}
                canMerge={canMerge}
                canEditPlacements={can('placements.edit')}
                onDone={refresh}
              />
            ) : (
              <CandidateCard
                key={c.id}
                c={c}
                canMerge={canMerge && tab === 'open'}
                onDone={refresh}
              />
            ),
          )}
        </div>
      )}
    </div>
  );
}
