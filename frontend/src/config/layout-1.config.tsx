import {
  BarChart3,
  Briefcase,
  Building2,
  CalendarCheck,
  CircleHelp,
  ClipboardList,
  FileUp,
  GitMerge,
  Handshake,
  LayoutDashboard,
  LifeBuoy,
  ListChecks,
  Scale,
  Settings,
  UserRound,
  Users,
} from 'lucide-react';
import { type MenuConfig } from './types';

// Draft navigation from planning doc 20 §3. Labels and order are to be
// validated with CAP-YEI at the design sign-off (G2). Items will be filtered
// by the user's permission (T-143); headings with no visible item are hidden.
export const MENU_SIDEBAR: MenuConfig = [
  { title: 'Overview', icon: LayoutDashboard, path: '/' },
  {
    title: 'My dashboard',
    icon: LayoutDashboard,
    path: '/me',
    permission: 'youth.self_service',
  },
  {
    title: 'My opportunities',
    icon: Briefcase,
    path: '/me/opportunities',
    permission: 'youth.self_service',
  },
  {
    title: 'My placement',
    icon: Briefcase,
    path: '/me/placement',
    permission: 'youth.self_service',
  },
  {
    title: 'My profile',
    icon: UserRound,
    path: '/me/profile',
    permission: 'youth.self_service',
  },
  { heading: 'Your company' },
  {
    title: 'Dashboard',
    icon: LayoutDashboard,
    path: '/employer',
    permission: 'employer.view_dashboard',
  },
  {
    title: 'Opportunities',
    icon: Briefcase,
    path: '/employer/opportunities',
    permission: 'employer.view_opportunities',
  },
  {
    title: 'Referrals',
    icon: ClipboardList,
    path: '/employer/referrals',
    permission: 'employer.view_referrals',
  },
  {
    title: 'Company profile',
    icon: Building2,
    path: '/employer/company',
    permission: 'employer.view_profile',
  },
  {
    title: 'People',
    icon: Users,
    path: '/employer/people',
    permission: 'employer.view_profile',
  },
  { heading: 'Participants' },
  {
    title: 'Youth',
    icon: Users,
    path: '/youth',
    permission: 'participants.view',
  },
  {
    title: 'Duplicates',
    icon: GitMerge,
    path: '/duplicates',
    permission: 'duplicates.review',
  },
  {
    title: 'Imports',
    icon: FileUp,
    path: '/imports',
    permission: 'imports.run',
  },
  {
    title: 'Support priority',
    icon: LifeBuoy,
    path: '/support',
    permission: 'participants.view_profile',
  },
  { heading: 'Placement' },
  {
    title: 'Opportunities',
    icon: Briefcase,
    path: '/opportunities',
    permission: 'employers.view',
  },
  {
    title: 'Employers',
    icon: Building2,
    path: '/employers',
    permission: 'employers.view',
  },
  {
    title: 'Referrals',
    icon: ClipboardList,
    path: '/referrals',
    permission: 'referrals.view',
  },
  {
    title: 'Cases',
    icon: ListChecks,
    path: '/cases',
    permission: 'referrals.view',
  },
  {
    title: 'Placements',
    icon: Handshake,
    path: '/placements',
    permission: 'placements.view',
  },
  {
    title: 'Follow-ups',
    icon: CalendarCheck,
    path: '/followups',
    permission: 'placements.view',
  },
  { heading: 'Insight' },
  {
    title: 'Reports',
    icon: BarChart3,
    path: '/reports',
    permission: 'reports.view_aggregate',
  },
  { heading: 'System' },
  {
    title: 'Rules',
    icon: Scale,
    path: '/rules',
    permission: 'intelligence.view',
  },
  {
    title: 'Administration',
    icon: Settings,
    path: '/administration',
    permission: 'config.view',
    children: [
      {
        title: 'Staff accounts',
        path: '/administration/users',
        permission: 'identity.view_users',
      },
      {
        title: 'Employer portal',
        path: '/administration/employer-portal',
        permission: 'config.view',
      },
      {
        title: 'Programmes',
        path: '/administration/programmes',
        permission: 'config.view',
      },
      {
        title: 'Cohorts',
        path: '/administration/cohorts',
        permission: 'config.view',
      },
      {
        title: 'Courses',
        path: '/administration/courses',
        permission: 'config.view',
      },
      {
        title: 'Cohort courses',
        path: '/administration/cohort-courses',
        permission: 'config.view',
      },
      {
        title: 'Training institutions',
        path: '/administration/institutions',
        permission: 'config.view',
      },
      {
        title: 'Sectors',
        path: '/administration/sectors',
        permission: 'config.view',
      },
      {
        title: 'Qualification levels',
        path: '/administration/qualification-levels',
        permission: 'config.view',
      },
      {
        title: 'Qualification grades',
        path: '/administration/qualification-grades',
        permission: 'config.view',
      },
      {
        title: 'Follow-up schedule',
        path: '/administration/followup-schedule',
        permission: 'config.view',
      },
      {
        title: 'Skills',
        path: '/administration/skills',
        permission: 'config.view',
      },
      {
        title: 'Counties',
        path: '/administration/counties',
        permission: 'config.view',
      },
      {
        title: 'Sub-counties',
        path: '/administration/sub-counties',
        permission: 'config.view',
      },
      {
        title: 'Wards',
        path: '/administration/wards',
        permission: 'config.view',
      },
    ],
  },
  { title: 'Help centre', icon: CircleHelp, path: '/help' },
];

/** Keep only what the user may open; drop headings left with nothing under them. */
export function filterMenu(
  items: MenuConfig,
  can: (p?: string) => boolean,
): MenuConfig {
  const visible = items
    .filter((i) => i.heading || can(i.permission))
    .map((i) =>
      i.children ? { ...i, children: filterMenu(i.children, can) } : i,
    );
  return visible.filter((item, idx) => {
    if (!item.heading) return true;
    const next = visible[idx + 1];
    return next !== undefined && !next.heading;
  });
}
