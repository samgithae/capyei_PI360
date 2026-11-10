import { Helmet } from 'react-helmet-async';
import {
  Toolbar,
  ToolbarDescription,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
import { EmptyState } from '@/components/states';

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="container-fluid">
      <Helmet>
        <title>{`${title} | PI 360`}</title>
      </Helmet>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>{title}</ToolbarPageTitle>
          <ToolbarDescription>
            Not built yet. Screens wait for the design sign-off (G2).
          </ToolbarDescription>
        </ToolbarHeading>
      </Toolbar>
      <EmptyState
        title="Not built yet"
        hint="This screen is planned; see the work breakdown."
      />
    </div>
  );
}
