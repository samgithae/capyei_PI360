import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { errorText } from '@/pages/cases/case-shared';
import { saveBlob } from '@/pages/participants/cv/download-cv-button';
import { useMutation } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { toast } from 'sonner';
import { postFile } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FormModal } from '@/components/shared/modals';

/** The list filters an export honours. Paging and sorting are never sent: the file holds every
 * matching row, not just the page on screen. */
const FILTER_KEYS = [
  'q',
  'programme',
  'cohort',
  'county',
  'status',
  'archived',
] as const;

/**
 * "Export" for a table. It downloads exactly the rows the filters above the table select, with the
 * columns the table shows. Only people holding the restricted `exports.identifiable` grant see it,
 * and each export needs a stated purpose; the server logs and audits every one.
 */
export function ExportButton({
  table,
  params,
  noun,
  total,
}: {
  /** Which table: the last part of `/exports/table/<table>`. */
  table: string;
  /** The page's current query string (filters, paging). */
  params: URLSearchParams;
  /** Plural noun for the dialog, e.g. "youth". */
  noun: string;
  /** Rows matching the filters, if known. */
  total?: number;
}) {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [format, setFormat] = useState('csv');
  const [purpose, setPurpose] = useState('');
  const [error, setError] = useState('');

  const filters = new URLSearchParams();
  for (const k of FILTER_KEYS) {
    const v = params.get(k);
    if (v) filters.set(k, v);
  }
  const query = filters.toString();

  const run = useMutation({
    mutationFn: () =>
      postFile(`/exports/table/${table}${query ? `?${query}` : ''}`, {
        format,
        purpose: purpose.trim(),
      }),
    onSuccess: ({ blob, filename }) => {
      saveBlob(blob, filename);
      toast.success(`Export downloaded: ${filename}`);
      setOpen(false);
      setPurpose('');
    },
    onError: (e) => setError(errorText(e)),
  });

  if (!can('exports.identifiable')) return null;

  const count =
    total === undefined
      ? `all ${noun} matching the filters`
      : `${total} ${noun} matching the current filters`;

  return (
    <>
      <Button
        variant="outline"
        className="ml-auto"
        onClick={() => {
          setError('');
          setOpen(true);
        }}
      >
        <Download />
        Export
      </Button>
      <FormModal
        open={open}
        onOpenChange={setOpen}
        title={`Export ${noun}`}
        description={`The file will hold ${count}, with the columns shown in the table plus gender and age. It contains names.`}
        submitLabel="Download"
        pending={run.isPending}
        error={error}
        onSubmit={() => {
          if (!purpose.trim()) {
            setError('State what the file is for.');
            return;
          }
          setError('');
          run.mutate();
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="export-format">File type</Label>
          <select
            id="export-format"
            className="block h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={format}
            onChange={(e) => setFormat(e.target.value)}
          >
            <option value="csv">CSV</option>
            <option value="xlsx">Excel</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="export-purpose">What is this file for?</Label>
          <Input
            id="export-purpose"
            value={purpose}
            maxLength={300}
            onChange={(e) => setPurpose(e.target.value)}
            placeholder="e.g. Mombasa follow-up calls"
          />
          <p className="text-xs text-muted-foreground">
            Recorded in the audit log with the filters you used. Keep the file
            secure and delete it when you are done.
          </p>
        </div>
      </FormModal>
    </>
  );
}
