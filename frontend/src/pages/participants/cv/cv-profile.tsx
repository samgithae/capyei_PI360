import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, Pencil } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { api, apiUrl } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ErrorState, LoadingState } from '@/components/states';
import { CvCompletion } from './cv-completion';
import { CvDocument } from './cv-document';
import { CvEditor } from './cv-editor';
import { cvPaths, type CvDoc, type CvProfileData } from './cv-types';
import { DownloadCvButton } from './download-cv-button';

type Mode = 'view' | 'edit';

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
  const [params, setParams] = useSearchParams();
  const asked = self && params.get('cv') === 'edit';
  const [mode, setMode] = useState<Mode>(asked ? 'edit' : 'view');
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

  // "Complete my CV" (here or on the dashboard) arrives as ?cv=edit: open the editor, and once
  // it has loaded (before that the page is too short to scroll that far) bring it into view.
  const scrollPending = useRef(false);
  useEffect(() => {
    if (!asked || !cv.data) return;
    scrollPending.current = true;
    setMode('edit');
    setParams(
      (old) => {
        const n = new URLSearchParams(old);
        n.delete('cv');
        return n;
      },
      { replace: true },
    );
  }, [asked, cv.data, setParams]);
  useEffect(() => {
    if (!scrollPending.current || mode !== 'edit' || !profile.data) return;
    scrollPending.current = false;
    const top = document.getElementById('my-cv')?.getBoundingClientRect().top;
    if (top !== undefined)
      window.scrollTo({
        top: Math.max(0, top + window.scrollY - 76),
        behavior: 'smooth',
      });
  }, [mode, profile.data]);

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
    <div id="my-cv" className={cn('scroll-mt-20 space-y-5', 'pb-20 sm:pb-0')}>
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

      {/* A youth's own completion card sits at the top of their profile page instead. */}
      {!self && (
        <CvCompletion
          cv={doc}
          self={false}
          onEdit={canEdit ? () => setMode('edit') : undefined}
        />
      )}

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
