import { useAuth } from '@/auth/auth-context';
import { COMPANY_ENDPOINTS, PeoplePanel } from '@/pages/employers/people-panel';
import { Helmet } from 'react-helmet-async';
import { PageHeader } from '@/components/shared/page-header';

/**
 * The company's people: one list. Everyone at the company PI 360 can reach, and, for those who can
 * sign in, their role and status. Anyone who can see the company profile sees the list; editing
 * a person needs `employer.edit_profile`, and sign-in access needs `employer.manage_staff`.
 */
export function EmployerPeoplePage() {
  const { can } = useAuth();
  const canAccess = can('employer.manage_staff');
  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>People | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'People' }]}
        title="People"
        description="Everyone at your company PI 360 can reach, and who can sign in to this portal."
      />
      <PeoplePanel
        endpoints={COMPANY_ENDPOINTS}
        noun="company"
        canEdit={can('employer.edit_profile')}
        canAccess={canAccess}
        showAccess={canAccess}
        description="Company admin can do everything. HR / Recruiter manages opportunities and replies to referrals. Hiring manager replies to referrals. Employer viewer can only look."
      />
    </div>
  );
}
