import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/shared/page-header';
import { ErrorState, LoadingState } from '@/components/states';
import type { ReportSummary } from './report-types';

/** The five stakeholder reports, one card each. Each opens on its own page. */
export function ReportsIndexPage() {
  const q = useQuery({
    queryKey: ['reports', 'index'],
    queryFn: () => api<{ reports: ReportSummary[] }>('/reporting/reports'),
  });

  return (
    <div className="space-y-5">
      <Helmet>
        <title>Reports</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Insight' }, { label: 'Reports' }]}
        title="Reports"
        description="Five reports for directors, management and donors. Open one, narrow it with the filters, then save it as a PDF or an Excel file."
      />
      {q.isPending && <LoadingState rows={5} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.data.reports.map((r) => (
            <li key={r.slug}>
              <Link to={`/reports/${r.slug}`} className="block h-full">
                <Card className="h-full transition-shadow hover:shadow-md">
                  <CardContent className="flex h-full flex-col gap-3 p-5">
                    <h2 className="text-base font-semibold text-foreground">
                      {r.title}
                    </h2>
                    <p className="text-sm text-muted-foreground">{r.purpose}</p>
                    <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                      <Badge variant="secondary" appearance="light">
                        For {r.audience.toLowerCase()}
                      </Badge>
                      <span className="flex items-center gap-1 text-sm font-medium text-primary">
                        Open <ArrowRight className="size-4" />
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
