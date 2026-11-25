import { useAuth } from '@/auth/auth-context';
import { RequireAuth, RequirePermission } from '@/auth/guards';
import { AccountPage } from '@/pages/account/account-page';
import { AccessGrantsPage } from '@/pages/admin/access-grants-page';
import {
  PortalSettingsPage,
  YouthSettingsPage,
} from '@/pages/admin/portal-settings-page';
import { REFERENCE_KINDS, ReferencePage } from '@/pages/admin/reference-page';
import { UsersPage } from '@/pages/admin/users-page';
import { CasePage } from '@/pages/cases/case-page';
import { CasesPage } from '@/pages/cases/cases-page';
import { PlacementsPage } from '@/pages/cases/placements-page';
import { DashboardListPage } from '@/pages/dashboard/dashboard-list-page';
import { DataQualityPage } from '@/pages/data-quality/data-quality-page';
import { EmployerCompanyPage } from '@/pages/employer/employer-company';
import { EmployerDashboardPage } from '@/pages/employer/employer-dashboard';
import {
  EmployerOpportunitiesPage,
  EmployerOpportunityPage,
} from '@/pages/employer/employer-opportunities';
import { EmployerPeoplePage } from '@/pages/employer/employer-people';
import {
  EmployerReferralPage,
  EmployerReferralsPage,
} from '@/pages/employer/employer-referrals';
import { EmployerPage } from '@/pages/employers/employer-page';
import { EmployerReviewsPage } from '@/pages/employers/employer-reviews-page';
import { EmployersPage } from '@/pages/employers/employers-page';
import { FollowUpPage } from '@/pages/followups/followup-page';
import { FollowUpsPage } from '@/pages/followups/followups-page';
import { FollowUpSchedulePage } from '@/pages/followups/schedule-page';
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
import { ReferralPage } from '@/pages/referrals/referral-page';
import { ReferralsPage } from '@/pages/referrals/referrals-page';
import { RegistrationsPage } from '@/pages/registrations/registrations-page';
import { ReportPage } from '@/pages/reports/report-page';
import { ReportsIndexPage } from '@/pages/reports/reports-index-page';
import { RetentionPage } from '@/pages/retention/retention-page';
import { RuleSetPage } from '@/pages/rules/rule-set-page';
import { RuleSettingsPage } from '@/pages/rules/rule-settings-page';
import { RuleVersionPage } from '@/pages/rules/rule-version-page';
import { RulesPage } from '@/pages/rules/rules-page';
import { SupportQueuePage } from '@/pages/support/support-queue-page';
import { ActivatePage } from '@/pages/youth/activate-page';
import { DashboardPage } from '@/pages/youth/dashboard-page';
import {
  MyOpportunitiesPage,
  MyOpportunityPage,
} from '@/pages/youth/my-opportunities';
import { MyPlacementPage } from '@/pages/youth/my-placement';
import { PortalPage } from '@/pages/youth/portal-page';
import { RegisterPage } from '@/pages/youth/register-page';
import { RegisterVerifyPage } from '@/pages/youth/register-verify-page';
import { Navigate, Route, Routes } from 'react-router';
import { Layout1 } from '@/components/layouts/layout-1';

/** A youth-only or employer-only account has no staff pages; each has its own home. */
function Home() {
  const { can } = useAuth();
  if (can('employer.portal') && !can('participants.view'))
    return <Navigate to="/employer" replace />;
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
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/register/verify" element={<RegisterVerifyPage />} />
      <Route path="/youth/activate" element={<ActivatePage />} />
      <Route
        path="/employer/activate"
        element={<ActivatePage audience="employer" />}
      />
      <Route element={<RequireAuth />}>
        <Route element={<Layout1 />}>
          <Route path="/" element={<Home />} />
          <Route path="/account" element={<AccountPage />} />
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
          <Route
            element={<RequirePermission permission="employer.view_dashboard" />}
          >
            <Route path="/employer" element={<EmployerDashboardPage />} />
          </Route>
          <Route
            element={
              <RequirePermission permission="employer.view_opportunities" />
            }
          >
            <Route
              path="/employer/opportunities"
              element={<EmployerOpportunitiesPage />}
            />
            <Route
              path="/employer/opportunities/:id"
              element={<EmployerOpportunityPage />}
            />
          </Route>
          <Route
            element={<RequirePermission permission="employer.view_referrals" />}
          >
            <Route
              path="/employer/referrals"
              element={<EmployerReferralsPage />}
            />
            <Route
              path="/employer/referrals/:id"
              element={<EmployerReferralPage />}
            />
          </Route>
          <Route
            element={<RequirePermission permission="employer.view_profile" />}
          >
            <Route path="/employer/company" element={<EmployerCompanyPage />} />
            <Route path="/employer/people" element={<EmployerPeoplePage />} />
          </Route>
          {/* Contacts and Team were two pages; old links land on the one list. */}
          <Route
            path="/employer/team"
            element={<Navigate to="/employer/people" replace />}
          />
          <Route
            element={<RequirePermission permission="reports.view_aggregate" />}
          >
            <Route path="/reports" element={<ReportsIndexPage />} />
            <Route path="/reports/:slug" element={<ReportPage />} />
          </Route>
          <Route path="/dashboard/list" element={<DashboardListPage />} />
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
            <Route path="/registrations" element={<RegistrationsPage />} />
          </Route>
          <Route
            element={<RequirePermission permission="dataquality.review" />}
          >
            <Route path="/data-quality" element={<DataQualityPage />} />
          </Route>
          <Route element={<RequirePermission permission="employers.review" />}>
            <Route
              path="/employers/reviews"
              element={<EmployerReviewsPage />}
            />
          </Route>
          <Route element={<RequirePermission permission="employers.view" />}>
            <Route path="/employers" element={<EmployersPage />} />
            <Route path="/employers/:id" element={<EmployerPage />} />
            <Route path="/opportunities" element={<OpportunitiesPage />} />
            <Route path="/opportunities/:id" element={<OpportunityPage />} />
          </Route>
          <Route
            element={
              <RequirePermission permission="participants.view_profile" />
            }
          >
            <Route path="/support" element={<SupportQueuePage />} />
          </Route>
          <Route element={<RequirePermission permission="referrals.view" />}>
            <Route path="/referrals" element={<ReferralsPage />} />
            <Route path="/referrals/:id" element={<ReferralPage />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/cases/:id" element={<CasePage />} />
          </Route>
          <Route element={<RequirePermission permission="placements.view" />}>
            <Route path="/placements" element={<PlacementsPage />} />
            <Route path="/followups" element={<FollowUpsPage />} />
            <Route path="/followups/:id" element={<FollowUpPage />} />
          </Route>
          <Route element={<RequirePermission permission="intelligence.view" />}>
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/rules/settings" element={<RuleSettingsPage />} />
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
            <Route
              path="/administration/followup-schedule"
              element={<FollowUpSchedulePage />}
            />
            <Route
              path="/administration/employer-portal"
              element={<PortalSettingsPage />}
            />
            <Route
              path="/administration/youth-settings"
              element={<YouthSettingsPage />}
            />
          </Route>
          <Route element={<RequirePermission permission="retention.view" />}>
            <Route
              path="/administration/retention"
              element={<RetentionPage />}
            />
          </Route>
          <Route
            element={<RequirePermission permission="identity.manage_roles" />}
          >
            <Route
              path="/administration/access-grants"
              element={<AccessGrantsPage />}
            />
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
