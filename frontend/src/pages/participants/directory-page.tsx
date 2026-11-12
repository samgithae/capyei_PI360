import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useSearchParams } from 'react-router';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DataCard,
  FilterSelect,
  Pager,
  ParticipantStatus,
  SearchBox,
} from '@/components/data-card';
import {
  BulkBar,
  RowActions,
  RowCheckbox,
  SelectAllHead,
  ShowArchived,
  useArchiveFlow,
  useSelection,
} from '@/components/shared/bulk';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { ReferenceImport } from '@/pages/admin/reference-import';
import { AddYouth } from './add-youth';
import { EditParticipant } from './participant-edit';

interface Row {
  id: string;
  name: string;
  gender: string;
  age: number | null;
  status: string;
  archived: boolean;
  county: string;
  programmes: string[];
  cohorts: string[];
}
interface Page {
  total: number;
  page_size: number;
  results: Row[];
}
interface Option {
  id: string;
  name: string;
  programme_id?: string;
}
interface Options {
  programmes: Option[];
  cohorts: Option[];
  counties: Option[];
}

const STATUSES = ['active', 'completed', 'withdrawn', 'unknown'];
const FILTERS = [
  'q',
  'programme',
  'cohort',
  'county',
  'status',
  'archived',
] as const;

/** Youth directory. With a cohort chosen it doubles as the cohort roster (T-058). */
export function DirectoryPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') ?? 0);
  const [editing, setEditing] = useState<string | null>(null);
  const showArchived = params.get('archived') === '1';
  const canEdit = can('participants.edit');
  const canArchive = can('records.archive');

  const options = useQuery({
    queryKey: ['participant-filters'],
    queryFn: () => api<Options>('/participants/filters'),
  });
  const page = useQuery({
    queryKey: ['participants', params.toString()],
    queryFn: () => api<Page>(`/participants?${params.toString()}`),
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const move = (to: number) => {
    const next = new URLSearchParams(params);
    next.set('offset', String(Math.max(to, 0)));
    setParams(next);
  };
  const cohorts = (options.data?.cohorts ?? []).filter(
    (c) =>
      !params.get('programme') || c.programme_id === params.get('programme'),
  );
  const data = page.data;
  const selection = useSelection(
    data?.results.map((p) => p.id) ?? [],
    params.toString(),
  );
  const archive = useArchiveFlow({
    path: '/participants',
    noun: 'participant',
    nounPlural: 'participants',
    queryKeys: ['participants'],
    onDone: selection.clear,
  });
  const filtered = FILTERS.some((f) => params.get(f));

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Youth | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Youth' }]}
        title="Youth"
        actions={
          <>
            <AddYouth />
            {can('imports.run') && (
              <Button asChild>
                <Link to="/imports/new">Import participants</Link>
              </Button>
            )}
            {can('participants.edit') && (
              <ReferenceImport
                kind="youth-capability"
                title="Youth skills and qualifications"
                columns="enrollment_no*, programme, type* (qualification, skill, experience, availability), value*, detail, months, year"
                endpoint="/participants/profile-import"
                templateEndpoint="/participants/profile-import-template"
                onDone={() => void 0}
              />
            )}
          </>
        }
      />

      {archive.dialog}
      {editing && (
        <EditParticipant id={editing} onClose={() => setEditing(null)} />
      )}

      <DataCard
        toolbar={
          <>
            <SearchBox
              placeholder="Search name or enrollment no."
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="All programmes"
              value={params.get('programme') ?? ''}
              options={options.data?.programmes ?? []}
              onChange={(v) => set('programme', v)}
            />
            <FilterSelect
              label="All cohorts"
              value={params.get('cohort') ?? ''}
              options={cohorts}
              onChange={(v) => set('cohort', v)}
            />
            <FilterSelect
              label="All counties"
              value={params.get('county') ?? ''}
              options={options.data?.counties ?? []}
              onChange={(v) => set('county', v)}
            />
            <FilterSelect
              label="Any status"
              value={params.get('status') ?? ''}
              options={STATUSES.map((s) => ({ id: s, name: s }))}
              onChange={(v) => set('status', v)}
              className="w-36 capitalize"
            />
            {canArchive && (
              <ShowArchived
                checked={showArchived}
                onChange={(v) => set('archived', v ? '1' : '')}
              />
            )}
            {filtered && (
              <Button variant="outline" onClick={() => setParams({})}>
                Clear
              </Button>
            )}
          </>
        }
        footer={
          data && data.total > 0 ? (
            <Pager
              offset={offset}
              pageSize={data.page_size}
              onPageSize={(n) => {
                const next = new URLSearchParams(params);
                next.set('page_size', String(n));
                next.delete('offset');
                setParams(next);
              }}
              total={data.total}
              onMove={move}
            />
          ) : undefined
        }
      >
        {page.isError && (
          <div className="p-5">
            <ErrorState error={page.error} onRetry={() => page.refetch()} />
          </div>
        )}
        {page.isPending && (
          <div className="p-5">
            <LoadingState />
          </div>
        )}
        {data && data.results.length > 0 && (
          <BulkBar
            count={selection.selected.length}
            noun="participant(s)"
            archived={showArchived}
            canArchive={canArchive}
            onArchive={() => archive.request(selection.selected, true)}
            onRestore={() => archive.request(selection.selected, false)}
            onClear={selection.clear}
          />
        )}
        {data && data.results.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                {canArchive && <SelectAllHead selection={selection} />}
                <TableHead>Name</TableHead>
                <TableHead>Programme</TableHead>
                <TableHead>Cohort</TableHead>
                <TableHead>County</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((p) => (
                <TableRow
                  key={p.id}
                  data-state={
                    selection.isSelected(p.id) ? 'selected' : undefined
                  }
                >
                  {canArchive && (
                    <TableCell>
                      <RowCheckbox
                        selection={selection}
                        id={p.id}
                        label={`Select ${p.name}`}
                      />
                    </TableCell>
                  )}
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/youth/${p.id}`}
                    >
                      {p.name}
                    </Link>
                  </TableCell>
                  <TableCell>{p.programmes.join(', ')}</TableCell>
                  <TableCell>{p.cohorts.join(', ')}</TableCell>
                  <TableCell>{p.county}</TableCell>
                  <TableCell>
                    <ParticipantStatus status={p.status} />
                  </TableCell>
                  <TableCell>
                    <RowActions
                      label={p.name}
                      viewTo={`/youth/${p.id}`}
                      archived={p.archived}
                      onEdit={canEdit ? () => setEditing(p.id) : undefined}
                      onArchive={
                        canArchive
                          ? () => archive.request([p.id], true)
                          : undefined
                      }
                      onRestore={
                        canArchive
                          ? () => archive.request([p.id], false)
                          : undefined
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {data && data.results.length === 0 && (
          <div className="p-5">
            <EmptyState
              title="No participants match"
              hint="Try changing or clearing the filters."
            />
          </div>
        )}
      </DataCard>
    </div>
  );
}
