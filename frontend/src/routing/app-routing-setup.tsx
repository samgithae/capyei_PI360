import { RequireAuth, RequirePermission } from '@/auth/guards';
import { UsersPage } from '@/pages/admin/users-page';
import { EmployerPage } from '@/pages/employers/employer-page';
import { EmployersPage } from '@/pages/employers/employers-page';
import { ImportBatchPage } from '@/pages/imports/import-batch-page';
import { ImportNewPage } from '@/pages/imports/import-new-page';
import { ImportsPage } from '@/pages/imports/imports-page';
import { LoginPage } from '@/pages/login-page';
import { OpportunitiesPage } from '@/pages/opportunities/opportunities-page';
import { OpportunityPage } from '@/pages/opportunities/opportunity-page';
import { OverviewPage } from '@/pages/overview-page';
import { DirectoryPage } from '@/pages/participants/directory-page';
import { DuplicatesPage } from '@/pages/participants/duplicates-page';
import { ProfilePage } from '@/pages/participants/profile-page';
import { PlaceholderPage } from '@/pages/placeholder-page';
import { Navigate, Route, Routes } from 'react-router';
import { Layout1 } from '@/components/layouts/layout-1';

const SECTIONS: [string, string, string][] = [
  ['/support', 'ydm.view', 'Support priority'],
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
          <Route element={<RequirePermission permission="participants.view" />}>
            <Route path="/youth" element={<DirectoryPage />} />
            <Route path="/youth/:id" element={<ProfilePage />} />
          </Route>
          <Route element={<RequirePermission permission="imports.run" />}>
            <Route path="/imports" element={<ImportsPage />} />
            <Route path="/imports/new" element={<ImportNewPage />} />
            <Route path="/imports/:id" element={<ImportBatchPage />} />
          </Route>
          <Route element={<RequirePermission permission="duplicates.review" />}>
            <Route path="/duplicates" element={<DuplicatesPage />} />
          </Route>
          <Route element={<RequirePermission permission="employers.view" />}>
            <Route path="/employers" element={<EmployersPage />} />
            <Route path="/employers/:id" element={<EmployerPage />} />
            <Route path="/opportunities" element={<OpportunitiesPage />} />
            <Route path="/opportunities/:id" element={<OpportunityPage />} />
          </Route>
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
