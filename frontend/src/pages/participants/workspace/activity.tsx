import type { ReferralRow } from '@/pages/referrals/referral-shared';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { shortDate } from './types';

interface Row {
  at: string;
  actor?: string;
  action: string;
  detail?: Record<string, string>;
}

const LABELS: Record<string, string> = {
  'participant.created': 'Record created',
  'participant.edited': 'Personal details updated',
  'participant.enrollment_added': 'Enrolment added',
  'participant.enrollment_edited': 'Enrolment updated',
  'participant.contacts_edited': 'Contact details updated',
  'participant.residence_edited': 'Residence updated',
  'participant.profile_edited': 'CV profile updated',
  'participant.profile_imported': 'Profile imported from a file',
  'participant.profile_verified': 'An entry was verified',
  'participant.profile_unverified': 'An entry was un-verified',
  'participant.photo_set': 'Photo changed',
  'participant.photo_removed': 'Photo removed',
  'participant.cv_downloaded': 'CV downloaded',
  'participant.archived': 'Record archived',
  'participant.restored': 'Record restored',
};
const STATUS: Record<string, string> = {
  pending: 'marked pending',
  verified: 'verified',
  rejected: 'rejected',
  needs_reassessment: 'needs reassessment',
};

export function describeAction(r: Row): string {
  if (r.action === 'participant.profile_verification') {
    const kind = r.detail?.kind ?? 'entry';
    return `A ${kind} ${STATUS[r.detail?.status ?? ''] ?? 'was reviewed'}`;
  }
  return (
    LABELS[r.action] ??
    r.action
      .replace(/^participant\./, '')
      .replace(/_/g, ' ')
      .replace(/^./, (c) => c.toUpperCase())
  );
}

/** Referral events as feed rows (participants cannot import referrals, so this runs in the page). */
export function referralEvents(rows: ReferralRow[]): Row[] {
  const out: Row[] = [];
  for (const r of rows) {
    if (r.referred_at)
      out.push({
        at: r.referred_at,
        action: `referral|${r.id}|Referred to ${r.opportunity} (${r.employer})`,
      });
    if (
      r.referred_at &&
      Date.parse(r.updated_at) - Date.parse(r.referred_at) > 60_000
    )
      out.push({
        at: r.updated_at,
        action: `referral|${r.id}|${r.opportunity}: ${r.stage_label}`,
      });
  }
  return out;
}

/** What happened to this record, newest first: staff changes (when allowed) plus referral steps. */
export function ActivityFeed({
  id,
  referrals = [],
  limit,
}: {
  id: string;
  referrals?: ReferralRow[];
  limit?: number;
}) {
  const q = useQuery({
    queryKey: ['participant-activity', id],
    queryFn: () => api<{ results: Row[] }>(`/participants/${id}/activity`),
    retry: false,
  });
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState rows={3} />;
  const rows = [...q.data.results, ...referralEvents(referrals)].sort((a, b) =>
    b.at.localeCompare(a.at),
  );
  const shown = limit ? rows.slice(0, limit) : rows;
  if (shown.length === 0)
    return (
      <EmptyState
        title="No activity yet"
        hint="Changes to this record will appear here."
      />
    );
  return (
    <ol className="space-y-3 text-sm">
      {shown.map((r, i) => {
        const [kind, refId, text] = r.action.split('|');
        return (
          <li key={`${r.at}-${i}`} className="flex gap-3">
            <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" />
            <div className="min-w-0">
              {kind === 'referral' ? (
                <Link
                  className="font-medium hover:text-primary"
                  to={`/referrals/${refId}`}
                >
                  {text}
                </Link>
              ) : (
                <p className="font-medium">{describeAction(r)}</p>
              )}
              <p className="text-xs text-muted-foreground">
                {shortDate(r.at)}
                {r.actor ? ` by ${r.actor}` : ''}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
