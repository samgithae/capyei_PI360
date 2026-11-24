import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { api, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
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
import { ExportButton } from '@/components/shared/export-button';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { AddYouth } from './add-youth';

interface Row {
  id: string;
  name: string;
  gender: string;
  age: number | null;
  status: string;
  review?: string;
  consent?: string;
  archived: boolean;
  county: string;
  projects: string[];
  cohorts: string[];
}
interface Page {
  total: number;
  page_size: number;
  similar_names?: boolean;
  results: Row[];
}
interface Option {
  id: string;
  name: string;
  project_id?: string;
}
interface Options {
  projects: Option[];
  cohorts: Option[];
  counties: Option[];
}

const STATUSES = ['active', 'completed', 'withdrawn', 'unknown'];
const FILTERS = [
  'q',
  'project',
  'cohort',
  'county',
  'status',
  'review',
  'archived',
] as const;

/** Youth directory. With a cohort chosen it doubles as the cohort roster (T-058). */
export function DirectoryPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') ?? 0);
  const navigate = useNavigate();
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
    (c) => !params.get('project') || c.project_id === params.get('project'),
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
  const qc = useQueryClient();
  const [reviewError, setReviewError] = useState('');
  const markReviewed = useMutation({
    mutationFn: (ids: string[]) =>
      post<{ marked: number }>('/participants/review/mark', { ids }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['participants'] });
      void qc.invalidateQueries({ queryKey: ['participant'] });
      selection.clear();
      setReviewError('');
    },
    onError: () => setReviewError('Could not mark them reviewed. Try again.'),
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
          </>
        }
      />

      {archive.dialog}

      <DataCard
        toolbar={
          <>
            <SearchBox
              placeholder="Search name or enrollment no."
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="All projects"
              value={params.get('project') ?? ''}
              options={options.data?.projects ?? []}
              onChange={(v) => set('project', v)}
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
            <FilterSelect
              label="Any review state"
              value={params.get('review') ?? ''}
              options={[{ id: 'needs_review', name: 'Needs review' }]}
              onChange={(v) => set('review', v)}
              className="w-44"
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
            <ExportButton
              table="youth"
              params={params}
              noun="youth"
              total={data?.total}
            />
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
        {data?.similar_names && (
          <p
            role="status"
            className="border-b px-5 py-2 text-sm text-muted-foreground"
          >
            No exact match for “{params.get('q')}”. Showing similar names.
          </p>
        )}
        {canEdit && selection.selected.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-2 text-sm">
            <Button
              size="sm"
              variant="outline"
              disabled={markReviewed.isPending}
              onClick={() => markReviewed.mutate(selection.selected)}
            >
              Mark reviewed
            </Button>
            <span className="text-muted-foreground">
              Clears the review flag on the selected youth that have one.
            </span>
            {reviewError && (
              <span role="alert" className="text-destructive">
                {reviewError}
              </span>
            )}
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
                {(canArchive || canEdit) && (
                  <SelectAllHead selection={selection} />
                )}
                <TableHead>Name</TableHead>
                <TableHead>Project</TableHead>
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
                  {(canArchive || canEdit) && (
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
                  <TableCell>{p.projects.join(', ')}</TableCell>
                  <TableCell>{p.cohorts.join(', ')}</TableCell>
                  <TableCell>{p.county}</TableCell>
                  <TableCell>
                    <ParticipantStatus status={p.status} />
                    {p.review === 'needs_review' && (
                      <Badge variant="warning" className="ms-2">
                        Needs review
                      </Badge>
                    )}
                    {p.consent === 'not_recorded' && (
                      <Badge variant="warning" className="ms-2">
                        No consent
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <RowActions
                      label={p.name}
                      viewTo={`/youth/${p.id}`}
                      archived={p.archived}
                      onEdit={
                        canEdit
                          ? () => navigate(`/youth/${p.id}/edit`)
                          : undefined
                      }
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
