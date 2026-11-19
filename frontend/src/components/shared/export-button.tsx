import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { errorText } from '@/pages/cases/case-shared';
import { saveBlob } from '@/pages/participants/cv/download-cv-button';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { toast } from 'sonner';
import { api, postFile } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  ExportFields,
  type ExportFieldGroup,
} from '@/components/shared/export-fields';
import { FormModal } from '@/components/shared/modals';

/** What each table's export honours. These match the keys the table's own list takes; paging and
 * sorting are never sent, because the file holds every matching row, not just the page on screen.
 * `names` says whether the file holds young people's names (company tables do not). `picker` means
 * the person chooses the fields first (Youth); the others export the columns the table shows. */
const TABLES = {
  youth: {
    filters: ['q', 'programme', 'cohort', 'county', 'status', 'archived'],
    names: true,
    picker: true,
  },
  employers: {
    filters: ['q', 'sector', 'county', 'status', 'archived'],
    names: false,
    picker: false,
  },
  opportunities: {
    filters: ['q', 'status', 'kind', 'awaiting', 'archived'],
    names: false,
    picker: false,
  },
  referrals: {
    filters: ['q', 'stage', 'mine'],
    names: true,
    picker: false,
  },
  placements: {
    filters: ['q', 'pathway', 'state'],
    names: true,
    picker: false,
  },
  followups: {
    filters: ['q', 'kind', 'state', 'mine'],
    names: true,
    picker: false,
  },
} as const;

export type ExportTable = keyof typeof TABLES;

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
  table: ExportTable;
  /** The page's current query string (filters, paging). */
  params: URLSearchParams;
  /** Plural noun for the dialog, e.g. "youth". */
  noun: string;
  /** Rows matching the filters, if known. */
  total?: number;
}) {
  const { can } = useAuth();
  const kind = TABLES[table];
  const [open, setOpen] = useState(false);
  const [format, setFormat] = useState('csv');
  const [purpose, setPurpose] = useState('');
  const [error, setError] = useState('');
  // null until the person changes something: then every field is ticked.
  const [chosen, setChosen] = useState<Set<string> | null>(null);

  const fieldList = useQuery({
    queryKey: ['export-fields', table],
    queryFn: () =>
      api<{ groups: ExportFieldGroup[] }>(`/exports/fields/${table}`),
    enabled: open && kind.picker && can('exports.identifiable'),
    staleTime: Infinity,
  });
  const groups = fieldList.data?.groups ?? [];
  const everyKey = groups.flatMap((g) => g.fields.map((f) => f.key));
  const selected = chosen ?? new Set(everyKey);
  const hasSensitive = groups.some((g) =>
    g.fields.some((f) => f.sensitive && selected.has(f.key)),
  );

  const filters = new URLSearchParams();
  for (const k of TABLES[table].filters) {
    const v = params.get(k);
    if (v) filters.set(k, v);
  }
  const query = filters.toString();

  const run = useMutation({
    mutationFn: () =>
      postFile(`/exports/table/${table}${query ? `?${query}` : ''}`, {
        format,
        purpose: purpose.trim(),
        ...(kind.picker
          ? { fields: everyKey.filter((k) => selected.has(k)) }
          : {}),
      }),
    onSuccess: ({ blob, filename }) => {
      saveBlob(blob, filename);
      toast.success(`Export downloaded: ${filename}`);
      setOpen(false);
      setPurpose('');
      setChosen(null);
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
        description={`The file will hold ${count}, ${
          kind.picker
            ? 'one row each, with the fields you choose below.'
            : 'with the columns shown in the table.'
        } ${kind.names ? 'It contains names.' : 'It has no names of young people.'}`}
        submitLabel="Download"
        pending={run.isPending}
        error={error}
        onSubmit={() => {
          if (kind.picker && fieldList.isPending) {
            setError('The list of fields is still loading.');
            return;
          }
          if (kind.picker && selected.size === 0) {
            setError('Choose at least one field.');
            return;
          }
          if (!purpose.trim()) {
            setError('State what the file is for.');
            return;
          }
          setError('');
          run.mutate();
        }}
      >
        {kind.picker &&
          (fieldList.isError ? (
            <p role="alert" className="text-sm text-destructive">
              The list of fields could not be loaded. Close this window and try
              again.
            </p>
          ) : (
            <>
              <ExportFields
                groups={groups}
                selected={selected}
                onChange={setChosen}
              />
              {hasSensitive && (
                <p className="text-xs text-amber-800">
                  The file will include contact, date of birth or address
                  details. Share it only with people who need it.
                </p>
              )}
            </>
          ))}
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
