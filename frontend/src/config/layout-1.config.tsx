import {
  BarChart3,
  Briefcase,
  Building2,
  CircleHelp,
  ClipboardList,
  FileUp,
  GitMerge,
  LayoutDashboard,
  LifeBuoy,
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
    title: 'My profile',
    icon: UserRound,
    path: '/me',
    permission: 'youth.self_service',
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
    permission: 'ydm.view',
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
    title: 'Referrals and cases',
    icon: ClipboardList,
    path: '/referrals',
    permission: 'referrals.view',
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
