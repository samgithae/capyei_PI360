import { RequireAuth, RequirePermission } from '@/auth/guards';
import { UsersPage } from '@/pages/admin/users-page';
import { LoginPage } from '@/pages/login-page';
import { OverviewPage } from '@/pages/overview-page';
import { PlaceholderPage } from '@/pages/placeholder-page';
import { Navigate, Route, Routes } from 'react-router';
import { Layout1 } from '@/components/layouts/layout-1';

const SECTIONS: [string, string, string][] = [
  ['/youth', 'participants.view', 'Youth'],
  ['/support', 'ydm.view', 'Support priority'],
  ['/opportunities', 'placements.view', 'Opportunities'],
  ['/employers', 'employers.view', 'Employers'],
  ['/referrals', 'referrals.view', 'Referrals and cases'],
  ['/reports', 'reports.view_aggregate', 'Reports'],
];

export function AppRoutingSetup() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout1 />}>
          <Route path="/" element={<OverviewPage />} />
          {SECTIONS.map(([path, permission, title]) => (
            <Route
              key={path}
              element={<RequirePermission permission={permission} />}
            >
              <Route path={path} element={<PlaceholderPage title={title} />} />
            </Route>
          ))}
          <Route
            element={<RequirePermission permission="identity.view_users" />}
          >
            <Route
              path="/administration"
              element={<Navigate to="/administration/users" replace />}
            />
            <Route path="/administration/users" element={<UsersPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
