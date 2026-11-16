import { CvDocument } from '@/pages/participants/cv/cv-document';
import {
  cvPaths,
  type CvDoc,
  type CvPaths,
} from '@/pages/participants/cv/cv-types';
import { DownloadCvButton } from '@/pages/participants/cv/download-cv-button';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, CircleHelp, ExternalLink, XCircle } from 'lucide-react';
import { Link } from 'react-router';
import { api, apiUrl } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Section } from '@/components/shared/info-card';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

export interface FitCheck {
  label: string;
  mandatory: boolean;
  outcome: 'pass' | 'fail' | 'unknown';
  note: string;
  source: string | null;
  verified: boolean | null;
}
export interface Fit {
  origin: string;
  available: boolean;
  reason?: string;
  group?: 'eligible' | 'eligible_with_unknowns' | 'not_eligible';
  met?: number;
  checked?: number;
  checks?: FitCheck[];
  missing?: string[];
  not_checked?: { label: string; reason?: string }[];
}

const VERDICT: Record<NonNullable<Fit['group']>, string> = {
  eligible: 'Meets every must-have requirement.',
  eligible_with_unknowns:
    'No must-have requirement is failed, but some could not be checked yet.',
  not_eligible: 'Does not meet at least one must-have requirement.',
};

const ICON = {
  pass: <CheckCircle2 className="size-4 text-success" aria-label="Met" />,
  fail: <XCircle className="size-4 text-destructive" aria-label="Not met" />,
  unknown: (
    <CircleHelp className="size-4 text-warning" aria-label="Not recorded" />
  ),
} as const;

/** The rule engine's note is for staff who maintain rules ("participant.skills is not recorded").
 * An unrecorded fact is said plainly; a met or failed check keeps its own note when it has one. */
const explain = (c: FitCheck) =>
  c.outcome === 'unknown'
    ? "Nothing recorded on the youth's profile for this yet."
    : c.note || (c.outcome === 'pass' ? 'Met.' : 'Not met.');

/**
 * Why this youth was put forward, in plain words: the Compatibility checks for this opportunity,
 * one line each. A youth who applied themselves says so first; the checks are then context.
 */
export function WhySuggested({
  id,
  origin,
  path = `/referrals/${id}/fit`,
}: {
  id: string;
  origin: string;
  /** The employer portal reads the same checks from its own route. */
  path?: string;
}) {
  const q = useQuery({
    queryKey: ['referral-fit', path],
    queryFn: () => api<Fit>(path),
    retry: false,
  });
  const fit = q.data;
  return (
    <Section
      title="Why this youth was suggested"
      description="How the youth's recorded qualifications, skills and experience line up with what the opportunity asks for."
    >
      <div className="space-y-4">
        {origin === 'trainee' && (
          <p className="rounded-md bg-muted px-3 py-2 text-sm">
            The youth applied for this opportunity themselves.
          </p>
        )}
        {q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : !fit ? (
          <LoadingState rows={3} />
        ) : !fit.available ? (
          <EmptyState title="No fit analysis yet" hint={fit.reason} />
        ) : (
          <>
            <p className="text-sm font-medium">
              {fit.group && VERDICT[fit.group]}{' '}
              <span className="font-normal text-muted-foreground">
                {fit.met} of {fit.checked} checks met.
              </span>
            </p>
            <ul className="divide-y divide-border rounded-md border border-border">
              {fit.checks?.map((c, i) => (
                <li key={`${c.label}-${i}`} className="flex gap-3 p-3 text-sm">
                  <span className="mt-0.5 shrink-0">{ICON[c.outcome]}</span>
                  <div className="min-w-0">
                    <p className="font-medium">
                      {c.label}{' '}
                      <span className="text-xs font-normal text-muted-foreground">
                        {c.mandatory ? 'Must have' : 'Nice to have'}
                      </span>
                    </p>
                    <p className="text-muted-foreground">{explain(c)}</p>
                  </div>
                </li>
              ))}
            </ul>
            {fit.not_checked && fit.not_checked.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Not checked (no structured value yet):{' '}
                {fit.not_checked.map((n) => n.label).join(', ')}.
              </p>
            )}
          </>
        )}
      </div>
    </Section>
  );
}

/**
 * Everything an employer needs to decide on an interview: the youth's CV exactly as the employer
 * would receive it, plus the two actions staff use to pass it on. National ID, date of birth,
 * scores and staff notes are never part of it; contact details appear only for staff who may see
 * them.
 */
export function CandidateProfile({
  participantId,
  paths = cvPaths(participantId, false),
  description = 'What the employer would see. Download the CV to send it on.',
  fullProfile = true,
}: {
  participantId: string;
  /** The employer portal serves the CV from its own referral routes. */
  paths?: Pick<CvPaths, 'cv' | 'pdf' | 'photo'>;
  description?: string;
  /** Staff may open the full youth record; an employer may not. */
  fullProfile?: boolean;
}) {
  const q = useQuery({
    queryKey: ['participant-cv', participantId, paths.cv],
    queryFn: () => api<CvDoc>(paths.cv),
    retry: false,
  });
  return (
    <Section
      title="Candidate profile"
      description={description}
      action={
        <div className="flex flex-wrap items-center gap-2">
          {fullProfile && (
            <Button variant="outline" asChild>
              <Link to={`/youth/${participantId}`}>
                <ExternalLink /> View full profile
              </Link>
            </Button>
          )}
          <DownloadCvButton path={paths.pdf} />
        </div>
      }
    >
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <LoadingState rows={4} />
      ) : (
        <CvDocument
          cv={q.data}
          photoUrl={q.data.has_photo ? apiUrl(paths.photo) : null}
        />
      )}
    </Section>
  );
}
