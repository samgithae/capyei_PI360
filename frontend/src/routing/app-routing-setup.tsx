import { OverviewPage } from '@/pages/overview-page';
import { PlaceholderPage } from '@/pages/placeholder-page';
import { Navigate, Route, Routes } from 'react-router';
import { Layout1 } from '@/components/layouts/layout-1';

const SECTIONS: [string, string][] = [
  ['/youth', 'Youth'],
  ['/support', 'Support priority'],
  ['/opportunities', 'Opportunities'],
  ['/employers', 'Employers'],
  ['/referrals', 'Referrals and cases'],
  ['/reports', 'Reports'],
  ['/admin', 'Administration'],
];

export function AppRoutingSetup() {
  return (
    <Routes>
      <Route element={<Layout1 />}>
        <Route path="/" element={<OverviewPage />} />
        {SECTIONS.map(([path, title]) => (
          <Route
            key={path}
            path={path}
            element={<PlaceholderPage title={title} />}
          />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
