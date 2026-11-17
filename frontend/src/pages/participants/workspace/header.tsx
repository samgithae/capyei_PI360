import { useAuth } from '@/auth/auth-context';
import {
  Archive,
  ArchiveRestore,
  ArrowLeft,
  Eye,
  MoreHorizontal,
  Pencil,
  Send,
  UserRound,
} from 'lucide-react';
import { Link } from 'react-router';
import { apiUrl } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { StatusBadge } from '@/components/shared/status-badge';
import { DownloadCvButton } from '../cv/download-cv-button';
import { useCv, useParticipantReferrals } from './queries';
import { isOpenStage } from './readiness';
import type { Detail } from './types';

/** Placement state in one word, from real referrals only. */
function placementBadge(stages: string[]) {
  if (stages.includes('placed'))
    return { label: 'Placed', variant: 'success' as const };
  if (stages.some(isOpenStage))
    return { label: 'In referral', variant: 'info' as const };
  return null;
}

/**
 * Who this is and what staff can do with them. Deliberately shows no national ID or date of
 * birth: this is the part of the page that is screenshotted, printed and shown on a projector.
 */
export function IdentityHeader({
  p,
  onRefer,
  onArchive,
  onViewCv,
  editing = false,
}: {
  p: Detail;
  onRefer?: () => void;
  onArchive?: () => void;
  onViewCv?: () => void;
  /** The edit page shows the same header, with a way back instead of the profile actions. */
  editing?: boolean;
}) {
  const { can } = useAuth();
  const cv = useCv(p.id);
  const referrals = useParticipantReferrals(p.id);
  const enrolment = p.enrollments[0];
  const placement = placementBadge(
    referrals.data?.results.map((r) => r.stage) ?? [],
  );
  const headline = cv.data?.headline;
  const canCv = can('participants.view_profile');
  const youthId = enrolment?.enrollment_no || `#${p.id.slice(0, 8)}`;
  const place = [p.county, p.age !== null ? `Age ${p.age}` : '', p.gender]
    .filter(Boolean)
    .join(' · ');

  return (
    <section
      aria-label="Youth identity"
      className="rounded-lg border border-border bg-card p-5 shadow-xs"
    >
      <div className="flex flex-wrap items-start gap-5">
        {cv.data?.has_photo ? (
          <img
            src={apiUrl(`/participants/${p.id}/photo`)}
            alt={`Photo of ${p.name}`}
            className="size-24 shrink-0 rounded-full border border-border object-cover"
          />
        ) : (
          <div
            aria-hidden
            className="flex size-24 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
          >
            <UserRound className="size-10" />
          </div>
        )}
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <h1 className="text-2xl font-semibold break-words">{p.name}</h1>
            {headline && (
              <p className="text-base break-words text-muted-foreground">
                {headline}
              </p>
            )}
            {place && <p className="text-sm text-muted-foreground">{place}</p>}
          </div>
          <p className="text-sm text-muted-foreground">
            ID {youthId}
            {enrolment && (
              <>
                {' · '}
                {[enrolment.programme, enrolment.cohort]
                  .filter(Boolean)
                  .join(' / ')}
              </>
            )}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={p.status} />
            {enrolment && enrolment.status !== p.status && (
              <Badge variant="secondary" appearance="light" size="sm">
                Enrolment: {enrolment.status}
              </Badge>
            )}
            {placement && (
              <Badge variant={placement.variant} appearance="light" size="sm">
                {placement.label}
              </Badge>
            )}
            {p.archived && (
              <Badge variant="warning" appearance="light" size="sm">
                Archived
              </Badge>
            )}
            {editing && (
              <Badge variant="primary" appearance="light" size="sm">
                Editing
              </Badge>
            )}
          </div>
        </div>
        {editing ? (
          <Button asChild variant="outline">
            <Link to={`/youth/${p.id}`}>
              <ArrowLeft /> Back to profile
            </Link>
          </Button>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {onRefer && can('referrals.edit') && !p.archived && (
              <Button onClick={onRefer}>
                <Send /> Refer to Opportunity
              </Button>
            )}
            {can('participants.edit') && (
              <Button asChild variant="outline">
                <Link to={`/youth/${p.id}/edit`}>
                  <Pencil /> Edit Profile
                </Link>
              </Button>
            )}
            {canCv && (
              <>
                <Button variant="outline" onClick={onViewCv}>
                  <Eye /> View CV
                </Button>
                <DownloadCvButton path={`/participants/${p.id}/cv.pdf`} />
              </>
            )}
            {onArchive && can('records.archive') && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    mode="icon"
                    aria-label="More actions"
                  >
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={onArchive}>
                    {p.archived ? <ArchiveRestore /> : <Archive />}
                    {p.archived ? 'Restore record' : 'Archive record'}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        )}
      </div>
      {p.archived && (
        <p className="mt-4 rounded-md border border-border bg-muted/40 p-3 text-sm">
          This participant is archived and hidden from lists and reports.
        </p>
      )}
    </section>
  );
}
