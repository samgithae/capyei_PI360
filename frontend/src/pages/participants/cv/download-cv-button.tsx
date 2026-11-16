import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { ApiError, apiFile } from '@/lib/api';
import { Button } from '@/components/ui/button';

/** Save a blob under a name by clicking a temporary link; works in every browser. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * "Download CV (PDF)". Every click asks the server for the CV again, so the file always reflects
 * what is saved now, never an unsaved form or a cached copy.
 */
export function DownloadCvButton({
  path,
  className,
}: {
  path: string;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = async () => {
    setBusy(true);
    setError('');
    try {
      const { blob, filename } = await apiFile(path);
      saveBlob(blob, filename);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : 'Could not download the CV.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={className}>
      <Button type="button" onClick={() => void run()} disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <Download />}
        {busy ? 'Preparing...' : 'Download CV (PDF)'}
      </Button>
      {error && (
        <p role="alert" className="mt-1 text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
