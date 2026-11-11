import { Helmet } from 'react-helmet-async';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState } from '@/components/states';

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="container-fluid">
      <Helmet>
        <title>{`${title} | PI 360`}</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: title }]}
        title={title}
        description="Not built yet. Screens wait for the design sign-off (G2)."
      />
      <EmptyState
        title="Not built yet"
        hint="This screen is planned; see the work breakdown."
      />
    </div>
  );
}
