import { useMemo, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { ReferenceImport } from '@/pages/admin/reference-import';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, apiUrl, post, upload } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { Notice } from '@/components/states';
import { CodePicker } from './code-picker';
import {
  ImportStepper,
  type Batch,
  type Inspection,
  type Template,
} from './shared';

const PARTICIPANT_DEFAULTABLE = [
  'project_code',
  'cohort_code',
  'course_code',
];
const PLACEMENT_DEFAULTABLE = ['project_code'];
const IGNORE = '';
const NEW = 'new';
const SKIP = '__skip__'; // Radix Select cannot hold an empty value

/** Steps 1-2: choose a file, then say what each column means. Nothing is stored until the
 * mapping is confirmed and the file is validated (the "dry run"). */
export function ImportNewPage() {
  const nav = useNavigate();
  const { can } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [seen, setSeen] = useState<Inspection | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [choice, setChoice] = useState<string>(NEW); // a saved template id, or NEW
  const [source, setSource] = useState('');
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [target, setTarget] = useState<'participants' | 'placements'>(
    'participants',
  );
  const DEFAULTABLE =
    target === 'placements' ? PLACEMENT_DEFAULTABLE : PARTICIPANT_DEFAULTABLE;

  const templates = useQuery({
    queryKey: ['import-templates'],
    queryFn: () => api<Template[]>('/imports/templates'),
  });

  // A fill-in workbook: Data sheet with the exact column names, instructions and valid codes.
  const sample = useMutation({
    mutationFn: async () => {
      const res = await fetch(apiUrl(`/imports/sample?target=${target}`), {
        credentials: 'include',
      });
      if (!res.ok) throw new Error('download failed');
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = `import-sample-${target}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: () => toast.error('Could not download the sample file.'),
  });

  const inspect = useMutation({
    mutationFn: (f: File) =>
      upload<Inspection>('/imports/inspect', { file: f, target }),
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
  }, [seen, mapping, defaults, DEFAULTABLE]);

  // A saved mapping that leaves out project/cohort/course needs a default for each.
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
          target,
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
        <PageHeader
          crumbs={[{ label: 'New import' }]}
          title="New import"
          actions={
            can('participants.edit') && (
              <ReferenceImport
                kind="youth-capability"
                title="Youth skills and qualifications"
                buttonLabel="Import skills & qualifications"
                columns="enrollment_no*, project, type* (qualification, skill, experience, availability), value*, detail, months, year"
                endpoint="/participants/profile-import"
                templateEndpoint="/participants/profile-import-template"
                onDone={() => void 0}
              />
            )
          }
        />
        <ImportStepper current={step} />

        {error && (
          <Notice tone="error" title="This could not be done">
            {error instanceof ApiError
              ? error.message
              : 'Something went wrong.'}
          </Notice>
        )}

        {!seen && (
          <Card className="max-w-xl">
            <CardContent className="space-y-3">
              <h2 className="font-medium">1. Choose the file</h2>
              <div className="space-y-1.5 text-sm">
                <span>What is in the file?</span>
                <SelectField
                  label="What is in the file?"
                  value={target}
                  options={[
                    { id: 'participants', name: 'People (enrollments)' },
                    {
                      id: 'placements',
                      name: 'Placements (employers and outcomes)',
                    },
                  ]}
                  onChange={(x) =>
                    setTarget(x as 'participants' | 'placements')
                  }
                />
              </div>
              <p className="text-sm text-muted-foreground">
                A .csv or .xlsx file (first sheet, headers in the first row).
                Choosing it only reads the headers. Nothing is saved yet.
              </p>
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed p-3 text-sm">
                <span className="min-w-0 flex-1 text-muted-foreground">
                  No file yet? Download a sample, fill it in and choose it
                  below. It has instructions and the codes to use.
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={sample.isPending}
                  onClick={() => sample.mutate()}
                >
                  <Download /> Download sample (.xlsx)
                </Button>
              </div>
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
            </CardContent>
          </Card>
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

            <Card>
              <CardContent className="space-y-3">
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
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-muted/40">
                          <TableHead>Column in the file</TableHead>
                          <TableHead>First row of your file</TableHead>
                          <TableHead>Means (PI 360 field)</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {seen.headers.map((h) => (
                          <TableRow key={h}>
                            <TableCell>{h}</TableCell>
                            <TableCell>
                              {seen.sample[h] || <em>(empty)</em>}
                            </TableCell>
                            <TableCell>
                              <Select
                                value={mapping[h] || SKIP}
                                onValueChange={(v) =>
                                  setMapping((m) => ({
                                    ...m,
                                    [h]: v === SKIP ? '' : v,
                                  }))
                                }
                              >
                                <SelectTrigger
                                  aria-label={`Field for ${h}`}
                                  className="w-72"
                                >
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value={SKIP}>
                                    Ignore this column
                                  </SelectItem>
                                  <SelectItem value={`extra:${h}`}>
                                    Keep as extra data (&ldquo;{h}&rdquo;)
                                  </SelectItem>
                                  {seen.fields.map((f) => (
                                    <SelectItem
                                      key={f.field}
                                      value={f.field}
                                      disabled={taken(f.field, h)}
                                    >
                                      {f.field}
                                      {f.required ? ' (required)' : ''}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    {missingRequired.length > 0 && (
                      <Notice
                        tone="warning"
                        title="Required fields not mapped yet"
                      >
                        {missingRequired.join(', ')}. Project, cohort and
                        course are usually not columns in a sheet: set them once
                        under &ldquo;Cohort defaults&rdquo; below.
                      </Notice>
                    )}
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-3">
                <h2 className="font-medium">Cohort defaults (optional)</h2>
                <p className="text-sm text-muted-foreground">
                  A project (e.g. Go Blue), a cohort (an intake at one
                  institution) and a course are set up in PI 360 reference data
                  and each has a short code. They are usually not a column in
                  your sheet, so search and pick the ones that apply to the
                  whole file. A default fills empty cells only and never
                  replaces a value that is in the file.
                </p>
                <div className="flex flex-wrap gap-2">
                  {DEFAULTABLE.map((f) => {
                    // Cohort and course codes belong to a project: once one is chosen, only
                    // show that project's.
                    const prog = defaults.project_code;
                    const options = (seen.reference_codes[f] ?? []).filter(
                      (o) =>
                        f === 'project_code' || !prog || o.project === prog,
                    );
                    return (
                      <CodePicker
                        key={f}
                        label={f.replace('_code', '')}
                        options={options}
                        value={defaults[f] ?? ''}
                        onChange={(code) =>
                          setDefaults({
                            ...defaults,
                            [f]: code,
                            // a new project invalidates the cohort and course picked before
                            ...(f === 'project_code'
                              ? { cohort_code: '', course_code: '' }
                              : {}),
                          })
                        }
                      />
                    );
                  })}
                </div>
                {defaultsNeeded.length > 0 && (
                  <Notice tone="warning" title="This mapping needs defaults">
                    {defaultsNeeded.join(', ')} are not columns in the saved
                    mapping.
                  </Notice>
                )}
              </CardContent>
            </Card>

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
