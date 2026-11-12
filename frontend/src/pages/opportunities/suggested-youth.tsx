import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, CircleHelp, RefreshCw, X } from 'lucide-react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Section } from '@/components/shared/info-card';
import { FormModal } from '@/components/shared/modals';
import { ErrorState, LoadingState } from '@/components/states';

interface Check {
  label: string;
  mandatory: boolean;
  outcome: 'pass' | 'fail' | 'unknown';
  note: string;
  source: string;
  verified: boolean | null;
}
interface Suggestion {
  participant_id: string;
  name: string;
  group: 'eligible' | 'eligible_with_unknowns' | 'not_eligible';
  score: number | null;
  met: number;
  checked: number;
  preferred_met: number;
  preferred_total: number;
  coverage: number | null;
  checks: Check[];
  missing: string[];
  not_checked: { label: string; reason: string }[];
}
interface Suggestions {
  available: boolean;
  reason?: string;
  rule?: { version: number };
  weights_pending?: boolean;
  requirements?: number;
  counts?: Record<string, number>;
  suggestions?: Suggestion[];
  truncated?: boolean;
}

const GROUPS = {
  eligible: { label: 'Eligible', variant: 'success' },
  eligible_with_unknowns: {
    label: 'Eligible, some facts missing',
    variant: 'warning',
  },
  not_eligible: { label: 'Not eligible', variant: 'destructive' },
} as const;
const OUTCOME = { pass: 'Meets', fail: 'Does not meet', unknown: 'Unknown' };

const MARK = {
  pass: { Icon: Check, cls: 'text-success' },
  fail: { Icon: X, cls: 'text-destructive' },
  unknown: { Icon: CircleHelp, cls: 'text-muted-foreground' },
} as const;

/** Youth ranked against this opportunity by the active Compatibility rule, each with the reasons
 * (what they meet, miss or have not recorded). Tick several and refer them in one go. A
 * suggestion only: the officer decides the referral. */
export function SuggestedYouth({
  id,
  positions,
  canRefer = false,
}: {
  id: string;
  /** Places on offer; "Select top N" picks that many. */
  positions?: number;
  /** Show the tick boxes and the Refer button (opportunity open and the user may refer). */
  canRefer?: boolean;
}) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['opportunity-suggestions', id],
    queryFn: () => api<Suggestions>(`/opportunities/${id}/suggestions`),
  });
  const [picked, setPicked] = useState<string[]>([]);
  const [dialog, setDialog] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const rows = q.data?.suggestions ?? [];
  const name = (pid: string) =>
    rows.find((r) => r.participant_id === pid)?.name ?? 'Youth';
  const toggle = (pid: string) =>
    setPicked((p) =>
      p.includes(pid) ? p.filter((x) => x !== pid) : [...p, pid],
    );

  const send = useMutation({
    mutationFn: () =>
      api<{
        created: { participant_id: string }[];
        skipped: { participant_id: string; message: string }[];
      }>('/referrals/bulk', {
        method: 'POST',
        body: JSON.stringify({
          opportunity_id: id,
          participant_ids: picked,
          note,
          submit: true,
        }),
      }),
    onSuccess: (r) => {
      const n = r.created.length;
      if (n)
        toast.success(n === 1 ? '1 referral sent.' : `${n} referrals sent.`);
      if (r.skipped.length)
        toast.error(
          r.skipped
            .map((s) => `${name(s.participant_id)}: ${s.message}`)
            .join('\n'),
        );
      for (const key of [
        'referrals',
        'referral-summary',
        'opportunity',
        'opportunity-suggestions',
      ])
        void qc.invalidateQueries({ queryKey: [key] });
      setPicked(r.skipped.map((s) => s.participant_id));
      setDialog(false);
      setNote('');
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not send.'),
  });

  const topN = () =>
    setPicked(
      rows
        .filter((r) => r.group !== 'not_eligible')
        .slice(0, positions ?? 1)
        .map((r) => r.participant_id),
    );

  return (
    <Section title="Suggested youth">
      {q.isPending ? (
        <LoadingState rows={3} />
      ) : q.isError ? (
        <ErrorState onRetry={() => void q.refetch()} />
      ) : !q.data.available ? (
        <p className="text-sm text-muted-foreground">{q.data.reason}</p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            From Compatibility rule version {q.data.rule?.version}. Ranked best
            first: eligible before eligible with gaps before not eligible, then
            by{' '}
            {q.data.weights_pending
              ? 'how many preferred requirements they meet'
              : 'fit score'}
            . This is a suggestion only: you decide who to refer.{' '}
            {q.data.counts?.no_data
              ? `${q.data.counts.no_data} of ${q.data.counts.visible} youth have no skills, qualifications or experience recorded, so they are not ranked.`
              : ''}
          </p>
          {q.data.requirements === 0 && (
            <p className="rounded-md border border-warning/40 bg-warning/10 p-2 text-sm">
              This opportunity has no requirements yet, so there is nothing to
              rank on. Add requirements (skills, qualification, experience) and
              the list will order itself.
            </p>
          )}
          {q.data.weights_pending && (
            <p className="rounded-md border p-2 text-xs text-muted-foreground">
              A percentage fit is not shown because the scoring weights have not
              been approved yet (Administration, Rules). Until then, ranking
              uses the number of preferred requirements each youth meets.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={q.isFetching}
              onClick={() => void q.refetch()}
            >
              <RefreshCw className={q.isFetching ? 'animate-spin' : ''} />
              {q.isFetching ? 'Refreshing...' : 'Refresh suggestions'}
            </Button>
            <span className="text-xs text-muted-foreground">
              Last updated{' '}
              {new Date(q.dataUpdatedAt).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
              . Refresh after youth profiles, requirements or rules change.
            </span>
          </div>
          {canRefer && rows.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={topN}>
                Select top {positions ?? 1}
              </Button>
              {picked.length > 0 && (
                <Button size="sm" variant="ghost" onClick={() => setPicked([])}>
                  Clear
                </Button>
              )}
              <Button
                size="sm"
                disabled={picked.length === 0}
                onClick={() => {
                  setError('');
                  setDialog(true);
                }}
              >
                Refer selected ({picked.length})
              </Button>
              {positions !== undefined && picked.length > positions && (
                <span className="text-xs text-muted-foreground">
                  {positions} position{positions === 1 ? '' : 's'} on offer; you
                  have selected {picked.length}.
                </span>
              )}
            </div>
          )}
          {rows.length === 0 && (
            <p className="text-sm">No youth with recorded facts to rank yet.</p>
          )}
          {rows.map((s, i) => {
            const g = GROUPS[s.group];
            return (
              <div
                key={s.participant_id}
                className="flex gap-3 rounded-md border p-3"
              >
                {canRefer && (
                  <Checkbox
                    aria-label={`Select ${s.name}`}
                    checked={picked.includes(s.participant_id)}
                    onCheckedChange={() => toggle(s.participant_id)}
                    className="mt-1"
                  />
                )}
                <span className="w-6 pt-0.5 text-sm text-muted-foreground">
                  {i + 1}.
                </span>
                <div className="min-w-0 flex-1 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-3">
                    <Link
                      className="font-medium text-primary hover:underline"
                      to={`/youth/${s.participant_id}`}
                    >
                      {s.name}
                    </Link>
                    <Badge variant={g.variant} appearance="light" size="sm">
                      {g.label}
                    </Badge>
                    {s.checked > 0 && (
                      <span className="text-sm">
                        Meets {s.met} of {s.checked}
                      </span>
                    )}
                    {s.preferred_total > 0 && (
                      <span className="text-sm text-muted-foreground">
                        Preferred: {s.preferred_met} of {s.preferred_total}
                      </span>
                    )}
                    {s.score !== null && (
                      <span className="text-sm">
                        Fit {s.score}%
                        {s.coverage !== null && s.coverage < 1
                          ? ` (from ${Math.round(s.coverage * 100)}% of the facts)`
                          : ''}
                      </span>
                    )}
                  </div>
                  <ul className="space-y-0.5 text-sm">
                    {s.checks.map((c, j) => {
                      const { Icon, cls } = MARK[c.outcome];
                      return (
                        <li key={j} className="flex items-start gap-1.5">
                          <Icon
                            aria-label={OUTCOME[c.outcome]}
                            className={`mt-0.5 size-3.5 shrink-0 ${cls}`}
                          />
                          <span>
                            {c.label}{' '}
                            <span className="text-muted-foreground">
                              ({c.mandatory ? 'required' : 'preferred'}
                              {c.source
                                ? `, ${c.source}${c.verified ? ', verified' : ''}`
                                : ''}
                              {c.note ? `; ${c.note}` : ''})
                            </span>
                          </span>
                        </li>
                      );
                    })}
                    {s.not_checked.map((n, j) => (
                      <li key={`n${j}`} className="text-muted-foreground">
                        Not checked: {n.label} ({n.reason})
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })}
          {q.data.truncated && (
            <p className="text-xs text-muted-foreground">
              Showing the best matches only.
            </p>
          )}
        </div>
      )}
      <FormModal
        open={dialog}
        onOpenChange={setDialog}
        title={`Refer ${picked.length} youth`}
        description="Each becomes its own referral to this opportunity and is sent straight on. Anyone who already has an open referral here is skipped, and referred youth leave this list."
        submitLabel={`Send ${picked.length} referral${picked.length === 1 ? '' : 's'}`}
        pending={send.isPending}
        error={error}
        onSubmit={() => {
          setError('');
          send.mutate();
        }}
      >
        <ul className="max-h-40 list-disc space-y-0.5 overflow-auto ps-5 text-sm">
          {picked.map((pid) => (
            <li key={pid}>
              {name(pid)}
              {rows.find((r) => r.participant_id === pid)?.group ===
                'not_eligible' && (
                <span className="text-destructive"> (not eligible)</span>
              )}
            </li>
          ))}
        </ul>
        <div className="space-y-1.5">
          <Label htmlFor="bulk-note">Note (optional, added to each)</Label>
          <Textarea
            id="bulk-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
      </FormModal>
    </Section>
  );
}
