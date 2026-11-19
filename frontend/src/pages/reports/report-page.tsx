import { useMemo } from 'react';
import { saveBlob } from '@/pages/participants/cv/download-cv-button';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Download, FileSpreadsheet, FileText, X } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useParams, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, postFile } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import {
  FILTER_LABELS,
  filterQuery,
  type FilterKey,
  type FilterOptions,
  type Report,
  type ReportSummary,
} from './report-types';
import { ReportView } from './report-view';

/** One report on its own page. The filters live in the address, so a view can be bookmarked or
 * sent to a colleague, and the file you export is exactly what is on screen. */
export function ReportPage() {
  const { slug = '' } = useParams();
  const [search, setSearch] = useSearchParams();

  const index = useQuery({
    queryKey: ['reports', 'index'],
    queryFn: () => api<{ reports: ReportSummary[] }>('/reporting/reports'),
  });
  const options = useQuery({
    queryKey: ['reports', 'filters'],
    queryFn: () => api<FilterOptions>('/reporting/reports/filters'),
    staleTime: 5 * 60_000,
  });
  const query = filterQuery(search);
  const report = useQuery({
    queryKey: ['reports', slug, query],
    queryFn: () => api<Report>(`/reporting/reports/${slug}?${query}`),
    retry: false,
  });
  const exporter = useMutation({
    mutationFn: (fmt: 'pdf' | 'xlsx') =>
      postFile(
        `/reporting/reports/${slug}/export?${filterQuery(search, { file_format: fmt })}`,
        {},
      ),
    onSuccess: ({ blob, filename }) => {
      saveBlob(blob, filename);
      toast.success(`Saved ${filename}`);
    },
    onError: (e) =>
      toast.error(
        e instanceof ApiError ? e.message : 'The file could not be made.',
      ),
  });

  const summary = index.data?.reports.find((r) => r.slug === slug);
  const set = (key: string, value: string) =>
    setSearch(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        // A cohort belongs to one programme; changing the programme drops a stale cohort.
        if (key === 'programme' || key === 'institution') next.delete('cohort');
        return next;
      },
      { replace: true },
    );
  const active = ['from', 'to', ...(summary?.filters ?? [])].some((k) =>
    search.get(k),
  );

  const cohorts = useMemo(() => {
    const all = options.data?.cohorts ?? [];
    const p = search.get('programme');
    const i = search.get('institution');
    return all.filter(
      (c) => (!p || c.programme_id === p) && (!i || c.institution_id === i),
    );
  }, [options.data, search]);

  const unknown =
    index.data && !summary
      ? true
      : report.error instanceof ApiError && report.error.status === 404;

  return (
    <div className="space-y-5">
      <Helmet>
        <title>{summary?.title ?? 'Report'}</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Insight' },
          { label: 'Reports', to: '/reports' },
          { label: summary?.title ?? 'Report' },
        ]}
        title={summary?.title ?? 'Report'}
        description={summary?.purpose}
        actions={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                disabled={!report.data || exporter.isPending}
              >
                <Download className="size-4" />
                {exporter.isPending ? 'Preparing…' : 'Export'}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => exporter.mutate('pdf')}>
                <FileText className="size-4" /> PDF document
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exporter.mutate('xlsx')}>
                <FileSpreadsheet className="size-4" /> Excel workbook
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        }
      />

      {index.data && (
        <nav aria-label="Reports" className="flex flex-wrap gap-2">
          {index.data.reports.map((r) => (
            <Link
              key={r.slug}
              to={`/reports/${r.slug}`}
              aria-current={r.slug === slug ? 'page' : undefined}
              className={
                r.slug === slug
                  ? 'rounded-full bg-primary px-3 py-1 text-sm font-medium text-primary-foreground'
                  : 'rounded-full border px-3 py-1 text-sm text-muted-foreground hover:text-primary'
              }
            >
              {r.title}
            </Link>
          ))}
        </nav>
      )}

      {unknown ? (
        <EmptyState
          title="That report does not exist"
          hint="Choose one from the list of reports."
          action={
            <Button asChild variant="outline" size="sm">
              <Link to="/reports">All reports</Link>
            </Button>
          }
        />
      ) : (
        <>
          {summary && (
            <Card>
              <CardContent className="flex flex-wrap items-end gap-3 p-4">
                {summary.filters.map((key: FilterKey) =>
                  key === 'period' ? (
                    <div key={key} className="flex items-end gap-2">
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="rep-from">From</Label>
                        <Input
                          id="rep-from"
                          type="date"
                          className="w-40"
                          value={search.get('from') ?? ''}
                          onChange={(e) => set('from', e.target.value)}
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="rep-to">To</Label>
                        <Input
                          id="rep-to"
                          type="date"
                          className="w-40"
                          value={search.get('to') ?? ''}
                          onChange={(e) => set('to', e.target.value)}
                        />
                      </div>
                    </div>
                  ) : (
                    <div key={key} className="flex flex-col gap-1.5">
                      <Label>{FILTER_LABELS[key].label}</Label>
                      <SelectField
                        label={FILTER_LABELS[key].label}
                        className="w-52"
                        emptyLabel={FILTER_LABELS[key].empty}
                        value={search.get(key) ?? ''}
                        options={
                          key === 'cohort'
                            ? cohorts
                            : (options.data?.[FILTER_LABELS[key].options] ?? [])
                        }
                        disabled={options.isPending}
                        onChange={(v) => set(key, v)}
                      />
                    </div>
                  ),
                )}
                {active && (
                  <Button
                    variant="ghost"
                    onClick={() => setSearch({}, { replace: true })}
                  >
                    <X className="size-4" /> Clear filters
                  </Button>
                )}
              </CardContent>
            </Card>
          )}
          {options.isError && (
            <ErrorState
              error={options.error}
              onRetry={() => options.refetch()}
            />
          )}
          {report.isPending && <LoadingState rows={6} />}
          {report.isError && !unknown && (
            <ErrorState error={report.error} onRetry={() => report.refetch()} />
          )}
          {report.data && <ReportView report={report.data} />}
        </>
      )}
    </div>
  );
}
