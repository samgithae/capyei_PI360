import { Helmet } from 'react-helmet-async';
import { PageHeader } from '@/components/shared/page-header';
import { TeamPanel } from './team-panel';

/** The company's own admin manages who can sign in and what each person may do. */
export function EmployerTeamPage() {
  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Team | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Team' }]}
        title="Team"
        description="Everyone at your company who can sign in, and what they may do."
      />
      <TeamPanel
        base="/employer/staff"
        rolesPath="/employer/roles"
        description="Company admin can do everything. HR / Recruiter manages opportunities and replies to referrals. Hiring manager replies to referrals. Employer viewer can only look."
      />
    </div>
  );
}
