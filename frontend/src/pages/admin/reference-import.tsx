import { useState } from 'react';
import { Download, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { ApiError, upload } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface Result {
  dry_run: boolean;
  rows: number;
  created: number;
  skipped: number;
  failed: number;
  errors: { row: number; field: string; message: string }[];
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

/** Import records from a CSV/Excel file: preview first (nothing saved), then confirm. */
export function ReferenceImport({
  kind,
  title,
  columns,
  onDone,
}: {
  kind: string;
  title: string;
  columns: string;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setFile(null);
    setResult(null);
    setError('');
  };

  const run = async (dry: boolean) => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const r = await upload<Result>(`/config/reference/${kind}/import`, {
        file,
        dry_run: dry ? '1' : '',
      });
      setResult(r);
      if (!dry) {
        toast.success(
          `Imported ${r.created} ${title.toLowerCase()}` +
            (r.skipped ? `, ${r.skipped} already existed` : '') +
            (r.failed ? `, ${r.failed} rows had errors` : ''),
        );
        onDone();
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Import failed.');
    } finally {
      setBusy(false);
    }
  };

  const template = async () => {
    const res = await fetch(
      `${API_BASE}/config/reference/${kind}/import-template`,
      {
        credentials: 'include',
      },
    );
    if (!res.ok) return toast.error('Could not download the template.');
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url;
    a.download = `${kind}-template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const previewed = result?.dry_run === true;
  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          reset();
          setOpen(true);
        }}
      >
        <Upload className="size-4" /> Import
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Import {title.toLowerCase()}</DialogTitle>
            <DialogDescription>
              Upload a .csv or .xlsx file. Existing records are skipped, never
              changed.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4 text-sm">
            <p>
              Columns: <span className="font-mono text-xs">{columns}</span>
            </p>
            <Button variant="ghost" className="h-auto p-0" onClick={template}>
              <Download className="size-4" /> Download a template
            </Button>
            <input
              type="file"
              aria-label="File to import"
              accept=".csv,.xlsx"
              className="block w-full text-sm"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setResult(null);
                setError('');
              }}
            />
            {error && (
              <p role="alert" className="text-destructive">
                {error}
              </p>
            )}
            {result && (
              <div role="status" className="space-y-2 rounded-md border p-3">
                <p className="font-medium">
                  {previewed ? 'Preview (nothing saved yet): ' : 'Done: '}
                  {result.created} {previewed ? 'to add' : 'added'},{' '}
                  {result.skipped} already exist, {result.failed} with errors
                  (of {result.rows} rows).
                </p>
                {result.errors.length > 0 && (
                  <ul className="max-h-40 list-disc space-y-1 overflow-auto pl-5 text-destructive">
                    {result.errors.map((e) => (
                      <li key={`${e.row}-${e.field}`}>
                        Row {e.row}: {e.message}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {result && !previewed ? 'Close' : 'Cancel'}
            </Button>
            {(!result || previewed) && (
              <Button
                variant={previewed ? 'outline' : 'primary'}
                disabled={!file || busy}
                onClick={() => void run(true)}
              >
                {busy && !previewed ? 'Checking...' : 'Preview'}
              </Button>
            )}
            {previewed && result.created > 0 && (
              <Button disabled={busy} onClick={() => void run(false)}>
                {busy ? 'Importing...' : `Import ${result.created}`}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
