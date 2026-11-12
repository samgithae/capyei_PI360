import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Section } from '@/components/shared/info-card';
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
  coverage: number | null;
  checks: Check[];
  missing: string[];
  not_checked: { label: string; reason: string }[];
}
interface Suggestions {
  available: boolean;
  reason?: string;
  rule?: { version: number };
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

/** Youth ranked against this opportunity by the active Compatibility rule. A suggestion only:
 * the officer decides the referral. */
export function SuggestedYouth({ id }: { id: string }) {
  const q = useQuery({
    queryKey: ['opportunity-suggestions', id],
    queryFn: () => api<Suggestions>(`/opportunities/${id}/suggestions`),
  });
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
            From Compatibility rule version {q.data.rule?.version}. This is a
            suggestion only: you decide who to refer.{' '}
            {q.data.counts?.no_data
              ? `${q.data.counts.no_data} of ${q.data.counts.visible} youth have no skills, qualifications or experience recorded, so they are not ranked.`
              : ''}
          </p>
          {q.data.suggestions?.length === 0 && (
            <p className="text-sm">No youth with recorded facts to rank yet.</p>
          )}
          {q.data.suggestions?.map((s) => {
            const g = GROUPS[s.group];
            return (
              <details key={s.participant_id} className="rounded-md border p-3">
                <summary className="flex cursor-pointer flex-wrap items-center gap-3">
                  <Link
                    className="font-medium text-primary hover:underline"
                    to={`/youth/${s.participant_id}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {s.name}
                  </Link>
                  <Badge variant={g.variant} appearance="light" size="sm">
                    {g.label}
                  </Badge>
                  {s.score !== null && (
                    <span className="text-sm">
                      Fit {s.score}%
                      {s.coverage !== null && s.coverage < 1
                        ? ` (from ${Math.round(s.coverage * 100)}% of the facts)`
                        : ''}
                    </span>
                  )}
                  {s.missing.length > 0 && (
                    <span className="text-xs text-muted-foreground">
                      Missing: {s.missing.join(', ')}
                    </span>
                  )}
                </summary>
                <ul className="mt-2 space-y-1 text-sm">
                  {s.checks.map((c, i) => (
                    <li key={i}>
                      <strong>{OUTCOME[c.outcome]}:</strong> {c.label}{' '}
                      <span className="text-muted-foreground">
                        ({c.mandatory ? 'mandatory' : 'preferred'}
                        {c.source
                          ? `, ${c.source}${c.verified ? ', verified' : ''}`
                          : ''}
                        {c.note ? `; ${c.note}` : ''})
                      </span>
                    </li>
                  ))}
                  {s.not_checked.map((n, i) => (
                    <li key={`n${i}`} className="text-muted-foreground">
                      Not checked: {n.label} ({n.reason})
                    </li>
                  ))}
                </ul>
              </details>
            );
          })}
          {q.data.truncated && (
            <p className="text-xs text-muted-foreground">
              Showing the best matches only.
            </p>
          )}
        </div>
      )}
    </Section>
  );
}
