import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, FileText, Pencil } from 'lucide-react';
import { api, apiUrl } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ErrorState, LoadingState } from '@/components/states';
import { CvDocument } from './cv-document';
import { CvEditor } from './cv-editor';
import { cvPaths, type CvDoc, type CvProfileData } from './cv-types';
import { DownloadCvButton } from './download-cv-button';

type Mode = 'view' | 'edit';

/** "CV Profile Completion: 75%": what is missing from the CV, separate from placement readiness. */
function Completion({
  cv,
  canEdit,
  onEdit,
}: {
  cv: CvDoc;
  canEdit: boolean;
  onEdit: () => void;
}) {
  const { percent, missing } = cv.completeness;
  return (
    <section
      aria-label="CV profile completion"
      className="space-y-3 rounded-lg border border-border bg-card p-5"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">CV Profile Completion: {percent}%</h3>
        {percent === 100 && (
          <CheckCircle2 className="size-5 text-success" aria-hidden />
        )}
      </div>
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="CV profile completion"
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
      {missing.length > 0 ? (
        <ul className="space-y-1 text-sm">
          {missing.map((m) => (
            <li key={m.key}>
              <span className="font-medium">{m.label}:</span>{' '}
              <span className="text-muted-foreground">{m.hint}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          The essentials are in place. Adding more makes the CV stronger.
        </p>
      )}
      {missing.length > 0 && canEdit && (
        <Button size="sm" variant="outline" onClick={onEdit}>
          <Pencil /> Complete my CV
        </Button>
      )}
    </section>
  );
}

/**
 * The CV of one youth, in three clearly separate modes: read it (View), change what is on it
 * (Edit), and download the PDF. A youth sees their own (`self`); staff see one by id.
 * Having no work experience does not lower the completion figure.
 */
export function CvProfile({
  id,
  self = false,
}: {
  id: string;
  self?: boolean;
}) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>('view');
  const [photoVersion, setPhotoVersion] = useState(() => Date.now());
  const paths = cvPaths(id, self);
  const canEdit = self || can('participants.edit');
  const who = self ? 'self' : id;
  const cvKey = ['participant-cv', who];
  const profileKey = ['participant-profile', who];

  const cv = useQuery({
    queryKey: cvKey,
    queryFn: () => api<CvDoc>(paths.cv),
    retry: false,
  });
  // The editable records load only when needed; the CV view reads the finished document.
  const profile = useQuery({
    queryKey: profileKey,
    queryFn: () =>
      self
        ? api<{ profile: CvProfileData }>('/youth/me').then((r) => r.profile)
        : api<CvProfileData>(paths.profile),
    retry: false,
    enabled: mode === 'edit' && canEdit,
  });

  const changed = () => {
    setPhotoVersion(Date.now());
    void qc.invalidateQueries({ queryKey: cvKey });
    void qc.invalidateQueries({ queryKey: profileKey });
  };

  if (cv.isError)
    return <ErrorState error={cv.error} onRetry={() => void cv.refetch()} />;
  if (!cv.data) return <LoadingState />;
  const doc = cv.data;

  const tab = (m: Mode, label: string, icon: React.ReactNode) => (
    <Button
      type="button"
      size="sm"
      variant={mode === m ? 'primary' : 'outline'}
      aria-pressed={mode === m}
      onClick={() => setMode(m)}
    >
      {icon} {label}
    </Button>
  );

  return (
    <div className={cn('space-y-5', 'pb-20 sm:pb-0')}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">
          {self ? 'My CV' : 'Curriculum Vitae'}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="CV mode" className="flex gap-2">
            {tab('view', 'View CV', <FileText />)}
            {canEdit && tab('edit', 'Edit details', <Pencil />)}
          </div>
          <DownloadCvButton path={paths.pdf} className="hidden sm:block" />
        </div>
      </div>

      <Completion cv={doc} canEdit={canEdit} onEdit={() => setMode('edit')} />

      {mode === 'view' && (
        <CvDocument
          cv={doc}
          photoUrl={
            doc.has_photo ? `${apiUrl(paths.photo)}?v=${photoVersion}` : null
          }
        />
      )}
      {mode === 'edit' &&
        (profile.isError ? (
          <ErrorState
            error={profile.error}
            onRetry={() => void profile.refetch()}
          />
        ) : !profile.data ? (
          <LoadingState />
        ) : (
          <CvEditor
            paths={paths}
            profile={profile.data}
            cv={doc}
            photoVersion={photoVersion}
            onChanged={changed}
          />
        ))}

      {/* On a phone the download stays in reach however far the page is scrolled. */}
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-background p-3 sm:hidden">
        <DownloadCvButton path={paths.pdf} className="[&_button]:w-full" />
      </div>
    </div>
  );
}
