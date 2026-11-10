import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { useNavigate } from 'react-router';
import { api, ApiError, post, upload } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
import { Notice } from '@/components/states';
import {
  ImportStepper,
  type Batch,
  type Inspection,
  type Template,
} from './shared';

const DEFAULTABLE = ['programme_code', 'cohort_code', 'course_code'];
const IGNORE = '';
const NEW = 'new';

/** Steps 1-2: choose a file, then say what each column means. Nothing is stored until the
 * mapping is confirmed and the file is validated (the "dry run"). */
export function ImportNewPage() {
  const nav = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [seen, setSeen] = useState<Inspection | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [choice, setChoice] = useState<string>(NEW); // a saved template id, or NEW
  const [source, setSource] = useState('');
  const [defaults, setDefaults] = useState<Record<string, string>>({});

  const templates = useQuery({
    queryKey: ['import-templates'],
    queryFn: () => api<Template[]>('/imports/templates'),
  });

  const inspect = useMutation({
    mutationFn: (f: File) =>
      upload<Inspection>('/imports/inspect', { file: f }),
    onSuccess: (data, f) => {
      setSeen(data);
      setMapping(data.suggested);
      setChoice(data.matching_templates[0] ?? NEW);
      setSource(
        f.name
          .replace(/\.[^.]+$/, '')
          .toLowerCase()
          .replace(/\W+/g, '-'),
      );
    },
  });

  const fitting = (templates.data ?? []).filter((t) =>
    seen?.matching_templates.includes(t.id),
  );

  const missingRequired = useMemo(() => {
    if (!seen) return [];
    const used = new Set(Object.values(mapping));
    return seen.fields
      .filter(
        (f) =>
          f.required &&
          !used.has(f.field) &&
          !(DEFAULTABLE.includes(f.field) && defaults[f.field]?.trim()),
      )
      .map((f) => f.field);
  }, [seen, mapping, defaults]);

  // A saved mapping that leaves out programme/cohort/course needs a default for each.
  const savedTemplate = fitting.find((t) => t.id === choice);
  const defaultsNeeded =
    choice === NEW || !savedTemplate
      ? []
      : DEFAULTABLE.filter(
          (f) =>
            !Object.values(savedTemplate.columns).includes(f) &&
            !defaults[f]?.trim(),
        );

  const start = useMutation({
    mutationFn: async () => {
      let templateId = choice;
      if (choice === NEW) {
        const t = await post<Template>('/imports/templates', {
          source,
          columns: Object.fromEntries(
            Object.entries(mapping).filter(([, f]) => f !== IGNORE),
          ),
        });
        templateId = t.id;
      }
      return upload<Batch>('/imports/batches', {
        template: templateId,
        file: file!,
        defaults: JSON.stringify(
          Object.fromEntries(
            Object.entries(defaults).filter(([, v]) => v.trim()),
          ),
        ),
      });
    },
    onSuccess: (b) => nav(`/imports/${b.id}`),
  });

  const taken = (field: string, header: string) =>
    Object.entries(mapping).some(([h, f]) => f === field && h !== header);
  const error = inspect.error ?? start.error;
  const step = !seen ? 1 : 2;

  return (
    <>
      <Helmet>
        <title>New import - PI 360</title>
      </Helmet>
      <div className="container-fluid space-y-5">
        <Toolbar>
          <ToolbarHeading>
            <ToolbarPageTitle text="New import" />
          </ToolbarHeading>
        </Toolbar>
        <ImportStepper current={step} />

        {error && (
          <Notice tone="error" title="This could not be done">
            {error instanceof ApiError
              ? error.message
              : 'Something went wrong.'}
          </Notice>
        )}

        {!seen && (
          <section className="rounded-lg border p-4 space-y-3 max-w-xl">
            <h2 className="font-medium">1. Choose the file</h2>
            <p className="text-sm text-muted-foreground">
              A .csv or .xlsx file (first sheet, headers in the first row).
              Choosing it only reads the headers. Nothing is saved yet.
            </p>
            <Input
              type="file"
              accept=".csv,.xlsx"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setFile(f);
                if (f) inspect.mutate(f);
              }}
            />
            {inspect.isPending && (
              <p className="text-sm">Reading the file...</p>
            )}
          </section>
        )}

        {seen && file && (
          <>
            <div className="text-sm text-muted-foreground">
              {file.name}: {seen.row_count} data rows, {seen.headers.length}{' '}
              columns
              {seen.empty_columns.length > 0 &&
                `, ${seen.empty_columns.length} empty (${seen.empty_columns.join(', ')})`}
              .
            </div>
            {seen.already_loaded && (
              <Notice tone="warning" title="This exact file was loaded before">
                Rows already loaded will be skipped, so nothing is created
                twice.
              </Notice>
            )}

            <section className="rounded-lg border p-4 space-y-3">
              <h2 className="font-medium">2. Say what each column means</h2>
              {fitting.length > 0 && (
                <div className="space-y-1 text-sm">
                  {fitting.map((t) => (
                    <label key={t.id} className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="tpl"
                        checked={choice === t.id}
                        onChange={() => setChoice(t.id)}
                      />
                      Use saved mapping &ldquo;{t.source}&rdquo; version{' '}
                      {t.version}
                    </label>
                  ))}
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="tpl"
                      checked={choice === NEW}
                      onChange={() => setChoice(NEW)}
                    />
                    Set up a new mapping (saved as a new version)
                  </label>
                </div>
              )}

              {choice === NEW && (
                <>
                  <label className="block text-sm max-w-sm">
                    Name for this kind of file
                    <Input
                      value={source}
                      onChange={(e) => setSource(e.target.value)}
                    />
                  </label>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th className="py-1">Column in the file</th>
                        <th>Means (PI 360 field)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {seen.headers.map((h) => (
                        <tr key={h} className="border-t">
                          <td className="py-1.5">{h}</td>
                          <td>
                            <select
                              aria-label={`Field for ${h}`}
                              className="h-8.5 rounded-md border bg-background px-2 text-sm"
                              value={mapping[h] ?? IGNORE}
                              onChange={(e) =>
                                setMapping((m) => ({
                                  ...m,
                                  [h]: e.target.value,
                                }))
                              }
                            >
                              <option value={IGNORE}>Ignore this column</option>
                              {seen.fields.map((f) => (
                                <option
                                  key={f.field}
                                  value={f.field}
                                  disabled={taken(f.field, h)}
                                >
                                  {f.field}
                                  {f.required ? ' (required)' : ''}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {missingRequired.length > 0 && (
                    <Notice
                      tone="warning"
                      title="Required fields not mapped yet"
                    >
                      {missingRequired.join(', ')}
                    </Notice>
                  )}
                </>
              )}
            </section>

            <section className="rounded-lg border p-4 space-y-2">
              <h2 className="font-medium">Cohort defaults (optional)</h2>
              <p className="text-sm text-muted-foreground">
                Set programme, cohort and course once for the whole file. A
                default fills empty cells only and never replaces a value that
                is in the file. Use the codes from reference data.
              </p>
              <div className="flex flex-wrap gap-2">
                {DEFAULTABLE.map((f) => (
                  <Input
                    key={f}
                    className="max-w-48"
                    placeholder={f.replace('_code', '')}
                    aria-label={`Default ${f.replace('_', ' ')}`}
                    value={defaults[f] ?? ''}
                    onChange={(e) =>
                      setDefaults({ ...defaults, [f]: e.target.value })
                    }
                  />
                ))}
              </div>
              {defaultsNeeded.length > 0 && (
                <Notice tone="warning" title="This mapping needs defaults">
                  {defaultsNeeded.join(', ')} are not columns in the saved
                  mapping.
                </Notice>
              )}
            </section>

            <div className="flex gap-2">
              <Button
                disabled={
                  start.isPending ||
                  defaultsNeeded.length > 0 ||
                  (choice === NEW &&
                    (missingRequired.length > 0 || !source.trim()))
                }
                onClick={() => start.mutate()}
              >
                {start.isPending ? 'Validating...' : 'Validate the file'}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setSeen(null);
                  setFile(null);
                  inspect.reset();
                  start.reset();
                }}
              >
                Choose another file
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Validating is a dry run: it checks every row and changes no
              participant data.
            </p>
          </>
        )}
      </div>
    </>
  );
}
