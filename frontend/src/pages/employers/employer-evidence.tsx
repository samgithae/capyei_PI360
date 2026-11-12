import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { Section } from '@/components/shared/info-card';
import { ErrorState, LoadingState } from '@/components/states';

export interface Indicator {
  label: string;
  source: string;
  count: number;
  of: number;
  text: string;
  percent: number | null;
  status: 'shown' | 'insufficient' | 'no_data';
}
export interface Evidence {
  period: { from: string; to: string; days: number };
  minimum_referrals: number;
  referrals_in_period: number;
  enough: boolean;
  summary: string;
  indicators: Indicator[];
}

const STATUS_TEXT = {
  shown: '',
  insufficient: 'Insufficient evidence',
  no_data: 'No data yet',
};

/** Module C: what referrals recorded in PI 360 say about this employer. Counts, period and
 * source for each indicator; there is no overall rating or score. */
export function EmployerEvidence({ id }: { id: string }) {
  const { can } = useAuth();
  const q = useQuery({
    queryKey: ['employer-evidence', id],
    queryFn: () => api<Evidence>(`/employers/${id}/evidence`),
    enabled: can('intelligence.view'),
  });
  if (!can('intelligence.view')) return null;
  return (
    <Section
      title="Referral evidence"
      description="Only referrals recorded in PI 360 are counted. This is evidence, not a rating."
    >
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <LoadingState rows={3} />
      ) : (
        <div className="space-y-3 text-sm">
          <p className={q.data.enough ? '' : 'text-warning'}>
            {q.data.summary}
          </p>
          <p className="text-xs text-muted-foreground">
            Period: {q.data.period.from} to {q.data.period.to} (
            {q.data.period.days} days).{' '}
            {can('intelligence.manage_rules') && (
              <Link className="text-primary" to="/rules/settings">
                Change the period or minimum
              </Link>
            )}
          </p>
          <ul className="divide-y">
            {q.data.indicators.map((i) => (
              <li key={i.label} className="py-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">{i.label}</span>
                  <span className="text-muted-foreground">
                    Source: {i.source}
                  </span>
                </div>
                <p>
                  {i.status === 'no_data' ? (
                    STATUS_TEXT.no_data
                  ) : (
                    <>
                      {i.text}
                      {i.percent !== null && ` (${i.percent}%)`}
                      {i.status === 'insufficient' && (
                        <span className="text-muted-foreground">
                          {' '}
                          · {STATUS_TEXT.insufficient}
                        </span>
                      )}
                    </>
                  )}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}
