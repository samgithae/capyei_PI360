import { useAuth } from '@/auth/auth-context';
import { RequireAuth, RequirePermission } from '@/auth/guards';
import { REFERENCE_KINDS, ReferencePage } from '@/pages/admin/reference-page';
import { UsersPage } from '@/pages/admin/users-page';
import { EmployerPage } from '@/pages/employers/employer-page';
import { EmployersPage } from '@/pages/employers/employers-page';
import { GuidePage } from '@/pages/help/guide-page';
import { HelpPage } from '@/pages/help/help-page';
import { ImportBatchPage } from '@/pages/imports/import-batch-page';
import { ImportNewPage } from '@/pages/imports/import-new-page';
import { ImportsPage } from '@/pages/imports/imports-page';
import { PromoteExtraPage } from '@/pages/imports/promote-extra-page';
import { LoginPage } from '@/pages/login-page';
import { OpportunitiesPage } from '@/pages/opportunities/opportunities-page';
import { OpportunityPage } from '@/pages/opportunities/opportunity-page';
import { OverviewPage } from '@/pages/overview-page';
import { DirectoryPage } from '@/pages/participants/directory-page';
import { DuplicatesPage } from '@/pages/participants/duplicates-page';
import { EditParticipant } from '@/pages/participants/participant-edit';
import { ProfilePage } from '@/pages/participants/profile-page';
import { PlaceholderPage } from '@/pages/placeholder-page';
import { ReferralPage } from '@/pages/referrals/referral-page';
import { ReferralsPage } from '@/pages/referrals/referrals-page';
import { RuleSetPage } from '@/pages/rules/rule-set-page';
import { RuleVersionPage } from '@/pages/rules/rule-version-page';
import { RulesPage } from '@/pages/rules/rules-page';
import { ActivatePage } from '@/pages/youth/activate-page';
import { DashboardPage } from '@/pages/youth/dashboard-page';
import {
  MyOpportunitiesPage,
  MyOpportunityPage,
} from '@/pages/youth/my-opportunities';
import { MyPlacementPage } from '@/pages/youth/my-placement';
import { PortalPage } from '@/pages/youth/portal-page';
import { Navigate, Route, Routes } from 'react-router';
import { Layout1 } from '@/components/layouts/layout-1';

const SECTIONS: [string, string, string][] = [
  ['/support', 'ydm.view', 'Support priority'],
  ['/reports', 'reports.view_aggregate', 'Reports'],
];

/** A youth-only account has no staff pages; its home is the portal. */
function Home() {
  const { can } = useAuth();
  return can('youth.self_service') && !can('participants.view') ? (
    <Navigate to="/me" replace />
  ) : (
    <OverviewPage />
  );
}

export function AppRoutingSetup() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/youth/activate" element={<ActivatePage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout1 />}>
          <Route path="/" element={<Home />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/help/:slug" element={<GuidePage />} />
          <Route
            element={<RequirePermission permission="youth.self_service" />}
          >
            <Route path="/me" element={<DashboardPage />} />
            <Route path="/me/placement" element={<MyPlacementPage />} />
            <Route path="/me/profile" element={<PortalPage />} />
            <Route path="/me/opportunities" element={<MyOpportunitiesPage />} />
            <Route
              path="/me/opportunities/:id"
              element={<MyOpportunityPage />}
            />
          </Route>
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
          <Route element={<RequirePermission permission="participants.edit" />}>
            <Route path="/youth/:id/edit" element={<EditParticipant />} />
          </Route>
          <Route element={<RequirePermission permission="imports.run" />}>
            <Route path="/imports" element={<ImportsPage />} />
            <Route path="/imports/new" element={<ImportNewPage />} />
            <Route path="/imports/promote" element={<PromoteExtraPage />} />
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
          <Route element={<RequirePermission permission="referrals.view" />}>
            <Route path="/referrals" element={<ReferralsPage />} />
            <Route path="/referrals/:id" element={<ReferralPage />} />
          </Route>
          <Route element={<RequirePermission permission="intelligence.view" />}>
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/rules/:id" element={<RuleSetPage />} />
            <Route path="/rules/versions/:id" element={<RuleVersionPage />} />
          </Route>
          <Route element={<RequirePermission permission="config.view" />}>
            {Object.keys(REFERENCE_KINDS).map((k) => (
              <Route
                key={k}
                path={`/administration/${k}`}
                element={<ReferencePage key={k} kind={k} />}
              />
            ))}
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
