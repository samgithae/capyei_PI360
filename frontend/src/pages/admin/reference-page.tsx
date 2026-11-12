import { useMemo, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard, useClientPage } from '@/components/data-card';
import { ManageLink } from '@/components/shared/manage-link';
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { ErrorState, LoadingState } from '@/components/states';
import { LinkCoursesDialog } from './link-courses-dialog';
import { ReferenceImport } from './reference-import';

type FieldType = 'text' | 'number' | 'date' | 'select' | 'fk';
interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean;
  options?: string[]; // for 'select'
  fk?: string; // reference kind the id points to
  /** Shown as a table column. */
  column?: boolean;
}
interface KindDef {
  title: string;
  singular: string;
  description: string;
  /** Records without a code and name (a course offered in a cohort). */
  unnamed?: boolean;
  /** A code is stable, so some kinds let the person type it (official county numbers). */
  codeHint?: string;
  fields: FieldDef[];
}
interface Row {
  id: string;
  code?: string;
  name?: string;
  active: boolean;
  [k: string]: unknown;
}

const STATUS = ['active', 'planned', 'closed'];

/** What can be managed, and the extra fields each kind carries. The server owns the rules. */
export const REFERENCE_KINDS: Record<string, KindDef> = {
  programmes: {
    title: 'Programmes',
    singular: 'programme',
    description: 'The funded programmes that youth belong to.',
    fields: [
      { key: 'funder', label: 'Funder', type: 'text', column: true },
      { key: 'start', label: 'Starts', type: 'date' },
      { key: 'end', label: 'Ends', type: 'date' },
      {
        key: 'status',
        label: 'Programme status',
        type: 'select',
        options: STATUS,
      },
    ],
  },
  cohorts: {
    title: 'Cohorts',
    singular: 'cohort',
    description:
      'An intake of youth at one training institution. Courses are attached under “Cohort courses”.',
    fields: [
      {
        key: 'programme',
        label: 'Programme',
        type: 'fk',
        fk: 'programmes',
        required: true,
        column: true,
      },
      {
        key: 'institution',
        label: 'Training institution',
        type: 'fk',
        fk: 'institutions',
        required: true,
        column: true,
      },
      {
        key: 'intake_year',
        label: 'Intake year',
        type: 'number',
        required: true,
        column: true,
      },
      {
        key: 'batch_no',
        label: 'Batch number',
        type: 'number',
        required: true,
      },
      { key: 'phase', label: 'Phase', type: 'number' },
      { key: 'year_of_study', label: 'Year of study', type: 'number' },
      { key: 'start', label: 'Starts', type: 'date' },
      { key: 'end', label: 'Ends', type: 'date' },
      {
        key: 'status',
        label: 'Cohort status',
        type: 'select',
        options: STATUS,
      },
    ],
  },
  courses: {
    title: 'Courses',
    singular: 'course',
    description: 'Courses a programme teaches.',
    fields: [
      {
        key: 'programme',
        label: 'Programme',
        type: 'fk',
        fk: 'programmes',
        required: true,
        column: true,
      },
      {
        key: 'default_sector',
        label: 'Default sector',
        type: 'fk',
        fk: 'sectors',
        column: true,
      },
      { key: 'level', label: 'Level', type: 'text' },
    ],
  },
  'cohort-courses': {
    title: 'Cohort courses',
    singular: 'cohort course',
    description:
      'Which courses a cohort runs. A youth is enrolled into one of these.',
    unnamed: true,
    fields: [
      {
        key: 'cohort',
        label: 'Cohort',
        type: 'fk',
        fk: 'cohorts',
        required: true,
        column: true,
      },
      {
        key: 'course',
        label: 'Course',
        type: 'fk',
        fk: 'courses',
        required: true,
        column: true,
      },
    ],
  },
  institutions: {
    title: 'Training institutions',
    singular: 'training institution',
    description: 'The colleges and centres that run cohorts.',
    fields: [
      {
        key: 'county',
        label: 'County',
        type: 'fk',
        fk: 'counties',
        required: true,
        column: true,
      },
      { key: 'ward', label: 'Ward', type: 'fk', fk: 'wards' },
      { key: 'kind', label: 'Type', type: 'select', options: ['vtc', 'other'] },
    ],
  },
  counties: {
    title: 'Counties',
    singular: 'county',
    description:
      'The 47 counties are already loaded. You can rename one or add another.',
    codeHint: 'Official county number, e.g. 48',
    fields: [],
  },
  'sub-counties': {
    title: 'Sub-counties',
    singular: 'sub-county',
    description: 'Sub-counties under each county.',
    fields: [
      {
        key: 'county',
        label: 'County',
        type: 'fk',
        fk: 'counties',
        required: true,
        column: true,
      },
    ],
  },
  wards: {
    title: 'Wards',
    singular: 'ward',
    description: 'Wards under each sub-county.',
    fields: [
      {
        key: 'sub_county',
        label: 'Sub-county',
        type: 'fk',
        fk: 'sub-counties',
        required: true,
        column: true,
      },
    ],
  },
  'qualification-levels': {
    title: 'Qualification levels',
    singular: 'qualification level',
    description:
      'The ladder of qualifications, lowest to highest. The rank orders them, so a rule can ask for "at least a diploma". Retiring one hides it from new records; existing records keep it.',
    fields: [
      {
        key: 'rank',
        label: 'Rank',
        type: 'number',
        required: true,
        column: true,
      },
    ],
  },
  'qualification-grades': {
    title: 'Qualification grades',
    singular: 'qualification grade',
    description:
      'The results a youth can have at each qualification level, such as A to E for secondary school. The rank orders them within the level (higher is better), so an opportunity can ask for "C or above". Retiring one hides it from new records; existing records keep it.',
    fields: [
      {
        key: 'level',
        label: 'Level',
        type: 'fk',
        fk: 'qualification-levels',
        required: true,
        column: true,
      },
      {
        key: 'rank',
        label: 'Rank',
        type: 'number',
        required: true,
        column: true,
      },
    ],
  },
  skills: {
    title: 'Skills',
    singular: 'skill',
    description:
      'Skills and competencies a youth may have and an opportunity may ask for. Retiring one hides it from new records; existing records keep it.',
    fields: [
      { key: 'category', label: 'Category', type: 'text', column: true },
    ],
  },
  sectors: {
    title: 'Sectors',
    singular: 'sector',
    description:
      'The industries employers and opportunities are grouped under. Retiring one hides it from new records; existing records keep it.',
    fields: [],
  },
};

/** A stable code made from the name, e.g. "Hospitality & Tourism" -> "hospitality-tourism". */
const codeFor = (name: string) =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);

// Clicking a county opens its sub-counties; clicking a sub-county opens its wards.
// Kinds that can be bulk-imported, with the columns the file needs (* = required).
const IMPORT_COLUMNS: Record<string, string> = {
  sectors: 'code*, name*',
  'qualification-levels':
    'code*, name*, rank* (a whole number; higher = more advanced)',
  skills: 'code*, name*, category',
  institutions: 'code*, name*, kind, county* (code or name)',
  programmes: 'code*, name*, funder, start, end, status',
  courses: 'code*, name*, programme*, level, sector',
  cohorts:
    'code*, name*, programme*, institution*, intake_year*, batch_no*, phase, year_of_study, start, end, status',
  'cohort-courses': 'cohort*, course*',
};

const DRILL: Record<string, { to: string; param: string }> = {
  counties: { to: 'sub-counties', param: 'county' },
  'sub-counties': { to: 'wards', param: 'sub_county' },
};

export function ReferencePage({ kind }: { kind: string }) {
  const def = REFERENCE_KINDS[kind];
  const { can } = useAuth();
  const qc = useQueryClient();
  const canManage = can('reference.manage');
  const [editing, setEditing] = useState<Row | 'new' | null>(null);
  const [linking, setLinking] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [codeEdited, setCodeEdited] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [sp] = useSearchParams();
  // the parent record this list is narrowed to, e.g. /administration/sub-counties?county=<id>
  const parentField = def.fields.find((f) => f.fk && sp.get(f.key));
  const parentId = parentField ? sp.get(parentField.key)! : '';
  const drill = DRILL[kind];

  const list = useQuery({
    queryKey: ['reference', kind],
    queryFn: () => api<Row[]>(`/config/reference/${kind}`),
  });
  // names for the parent records this kind points to
  const fkKinds = [
    ...new Set([
      ...def.fields.filter((f) => f.fk).map((f) => f.fk!),
      // cohort and course pickers label each option with its programme
      ...(def.fields.some((f) => f.fk === 'cohorts' || f.fk === 'courses')
        ? ['programmes']
        : []),
    ]),
  ];
  const parents = useQueries({
    queries: fkKinds.map((k) => ({
      queryKey: ['reference', k],
      queryFn: () => api<Row[]>(`/config/reference/${k}`),
    })),
  });
  const parentRows = useMemo(
    () => Object.fromEntries(fkKinds.map((k, i) => [k, parents[i].data ?? []])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fkKinds.join(), parents.map((p) => p.dataUpdatedAt).join()],
  );
  const nameOf = (k: string, id: unknown) =>
    ((parentRows[k] ?? []) as Row[]).find((r) => r.id === id)?.name ?? '';

  const rowLabel = (r: Row) =>
    def.unnamed
      ? `${nameOf('cohorts', r.cohort)} / ${nameOf('courses', r.course)}`
      : (r.name ?? '');

  const refresh = () => {
    // anything else that lists these (filters, pickers, the add-youth wizard) must reload
    void qc.invalidateQueries({ queryKey: ['reference'] });
    for (const k of [
      'employer-filters',
      'participant-filters',
      'offerings',
      'sectors-admin',
    ])
      void qc.invalidateQueries({ queryKey: [k] });
  };

  const body = (creating: boolean) => {
    const out: Record<string, unknown> = {};
    if (!def.unnamed) {
      out.name = name.trim();
      if (creating) out.code = code.trim();
    }
    for (const f of def.fields) {
      const raw = (form[f.key] ?? '').trim();
      if (f.type === 'select' || f.type === 'text') {
        if (raw !== '' || !creating) out[f.key] = raw;
      } else if (raw !== '') {
        out[f.key] = f.type === 'number' ? Number(raw) : raw;
      } else if (!creating) {
        out[f.key] = null;
      }
    }
    return out;
  };

  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'Could not save.');

  const save = useMutation({
    mutationFn: () =>
      editing === 'new'
        ? post(`/config/reference/${kind}`, body(true))
        : api(`/config/reference/${kind}/${(editing as Row).id}`, {
            method: 'PATCH',
            body: JSON.stringify(body(false)),
          }),
    onSuccess: () => {
      toast.success(editing === 'new' ? 'Added' : 'Saved');
      setEditing(null);
      refresh();
    },
    onError: fail,
  });

  const toggle = useMutation({
    mutationFn: (r: Row) =>
      post(
        `/config/reference/${kind}/${r.id}/${r.active ? 'deactivate' : 'reactivate'}`,
        { reason: '' },
      ),
    onSuccess: refresh,
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : 'Could not update.'),
  });

  const open = (r: Row | 'new') => {
    setEditing(r);
    setError('');
    if (r === 'new') {
      setName('');
      setCode('');
      setCodeEdited(false);
      setForm(
        Object.fromEntries(
          def.fields
            .filter((f) => f.type === 'select')
            .map((f) => [f.key, f.options![0]])
            .concat(parentField ? [[parentField.key, parentId]] : []),
        ),
      );
    } else {
      setName(r.name ?? '');
      setForm(
        Object.fromEntries(
          def.fields.map((f) => [
            f.key,
            r[f.key] == null ? '' : String(r[f.key]),
          ]),
        ),
      );
    }
  };

  const rows = (list.data ?? []).filter((r) => {
    const q = search.trim().toLowerCase();
    return (
      (!parentField || r[parentField.key] === parentId) &&
      (!q ||
        rowLabel(r).toLowerCase().includes(q) ||
        (r.code ?? '').toLowerCase().includes(q))
    );
  });
  const paged = useClientPage(rows);
  const parentName = parentField ? nameOf(parentField.fk!, parentId) : '';
  const parentUp =
    parentField?.fk === 'counties'
      ? null
      : parentField
        ? {
            to: `/administration/sub-counties?county=${
              ((parentRows['sub-counties'] as Row[]).find(
                (r) => r.id === parentId,
              )?.county as string | undefined) ?? ''
            }`,
            label: 'Back to sub-counties',
          }
        : null;
  const columns = def.fields.filter((f) => f.column);

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>{def.title} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Administration' }, { label: def.title }]}
        title={parentName ? `${def.title} in ${parentName}` : def.title}
        description={def.description}
        actions={
          canManage && (
            <div className="flex gap-2">
              {IMPORT_COLUMNS[kind] && (
                <ReferenceImport
                  kind={kind}
                  title={def.title}
                  columns={IMPORT_COLUMNS[kind]}
                  onDone={() => {
                    void qc.invalidateQueries({ queryKey: ['reference'] });
                  }}
                />
              )}
              <Button
                onClick={() =>
                  kind === 'cohort-courses' ? setLinking(true) : open('new')
                }
              >
                Add {def.singular}
              </Button>
            </div>
          )
        }
      />
      <DataCard
        title={
          parentName
            ? `${def.title} in ${parentName}`
            : `All ${def.title.toLowerCase()}`
        }
        footer={paged.pager}
        toolbar={
          <>
            {parentField && (
              <Button variant="outline" asChild>
                <Link to={parentUp?.to ?? `/administration/${parentField.fk}`}>
                  {parentUp?.label ?? 'All counties'}
                </Link>
              </Button>
            )}
            <Input
              aria-label={`Search ${def.title.toLowerCase()}`}
              placeholder="Search…"
              className="w-56"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </>
        }
      >
        {list.isLoading ? (
          <LoadingState />
        ) : list.isError ? (
          <ErrorState error={list.error} onRetry={() => void list.refetch()} />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40">
                  <TableHead>{def.unnamed ? 'Offering' : 'Name'}</TableHead>
                  {!def.unnamed && <TableHead>Code</TableHead>}
                  {columns
                    .filter(() => !def.unnamed)
                    .map((f) => (
                      <TableHead key={f.key}>{f.label}</TableHead>
                    ))}
                  <TableHead>Status</TableHead>
                  {canManage && <TableHead />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.rows.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-medium">
                      {drill ? (
                        <Link
                          className="text-primary hover:underline"
                          to={`/administration/${drill.to}?${drill.param}=${r.id}`}
                        >
                          {rowLabel(r)}
                        </Link>
                      ) : (
                        rowLabel(r)
                      )}
                    </TableCell>
                    {!def.unnamed && (
                      <TableCell className="text-muted-foreground">
                        {r.code}
                      </TableCell>
                    )}
                    {columns
                      .filter(() => !def.unnamed)
                      .map((f) => (
                        <TableCell key={f.key}>
                          {f.fk
                            ? nameOf(f.fk, r[f.key])
                            : r[f.key] == null
                              ? ''
                              : String(r[f.key])}
                        </TableCell>
                      ))}
                    <TableCell>
                      <Badge
                        variant={r.active ? 'success' : 'secondary'}
                        appearance="light"
                      >
                        {r.active ? 'Active' : 'Retired'}
                      </Badge>
                    </TableCell>
                    {canManage && (
                      <TableCell className="space-x-2 text-end">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => open(r)}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => toggle.mutate(r)}
                        >
                          {r.active ? 'Retire' : 'Reactivate'}
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {rows.length === 0 && (
              <p className="px-5 py-3 text-xs text-muted-foreground">
                No {def.title.toLowerCase()} found.
              </p>
            )}
          </>
        )}
      </DataCard>

      {kind === 'cohort-courses' && (
        <LinkCoursesDialog
          open={linking}
          onOpenChange={setLinking}
          cohorts={parentRows['cohorts'] as Row[]}
          courses={parentRows['courses'] as Row[]}
          programmes={parentRows['programmes'] as Row[]}
          links={list.data ?? []}
          onDone={refresh}
        />
      )}
      <FormModal
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        title={`${editing === 'new' ? 'Add' : 'Edit'} ${def.singular}`}
        submitLabel={editing === 'new' ? 'Add' : 'Save'}
        pending={save.isPending}
        error={error}
        onSubmit={() => {
          const missing = def.fields.find(
            (f) => f.required && !(form[f.key] ?? '').trim(),
          );
          if (!def.unnamed && !name.trim())
            return setError('A name is required.');
          if (editing === 'new' && !def.unnamed && !code.trim())
            return setError('A code is required.');
          if (missing) return setError(`${missing.label} is required.`);
          setError('');
          save.mutate();
        }}
      >
        {!def.unnamed && (
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input
              aria-label="Name"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (!codeEdited) setCode(codeFor(e.target.value));
              }}
              autoFocus
            />
          </div>
        )}
        {editing === 'new' && !def.unnamed && (
          <div className="space-y-1.5">
            <Label>Code</Label>
            <Input
              aria-label="Code"
              placeholder={def.codeHint ?? 'Made from the name; stays fixed'}
              value={code}
              onChange={(e) => {
                setCode(e.target.value);
                setCodeEdited(true);
              }}
            />
            <p className="text-xs text-muted-foreground">
              The code cannot be changed later; the name can.
            </p>
          </div>
        )}
        {def.fields.map((f) => (
          <div key={f.key} className="space-y-1.5">
            <Label>
              {f.label}
              {f.required && ' *'}
            </Label>
            {f.type === 'fk' || f.type === 'select' ? (
              <SelectField
                label={f.label}
                className="w-full capitalize"
                emptyLabel={f.required ? undefined : 'None'}
                value={form[f.key] ?? ''}
                options={
                  f.type === 'select'
                    ? f.options!.map((o) => ({ id: o, name: o }))
                    : (parentRows[f.fk!] as Row[])
                        .filter((p) => p.active || p.id === form[f.key])
                        .map((p) => ({
                          id: p.id,
                          name:
                            f.fk === 'cohorts' || f.fk === 'courses'
                              ? `${p.name} (${nameOf('programmes', p.programme) || p.code})`
                              : (p.name ?? ''),
                        }))
                }
                onChange={(x) => setForm((p) => ({ ...p, [f.key]: x }))}
              />
            ) : (
              <Input
                aria-label={f.label}
                type={f.type}
                value={form[f.key] ?? ''}
                onChange={(e) =>
                  setForm((p) => ({ ...p, [f.key]: e.target.value }))
                }
              />
            )}
            {f.type === 'fk' && (
              <ManageLink
                missing={f.label}
                to={`/administration/${f.fk}`}
                label={`Add or manage ${f.label.toLowerCase()}`}
              />
            )}
          </div>
        ))}
      </FormModal>
    </div>
  );
}
