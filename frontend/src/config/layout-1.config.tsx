import {
  BarChart3,
  Briefcase,
  Building2,
  ClipboardList,
  LayoutDashboard,
  LifeBuoy,
  Settings,
  Users,
} from 'lucide-react';
import { type MenuConfig } from './types';

// Draft navigation from planning doc 20 §3. Labels and order are to be
// validated with CAP-YEI at the design sign-off (G2). Items will be filtered
// by the user's permission (T-143); headings with no visible item are hidden.
export const MENU_SIDEBAR: MenuConfig = [
  { title: 'Overview', icon: LayoutDashboard, path: '/' },
  { heading: 'Participants' },
  {
    title: 'Youth',
    icon: Users,
    path: '/youth',
    permission: 'participants.view',
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
    permission: 'placements.view',
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
    title: 'Administration',
    icon: Settings,
    path: '/administration',
    permission: 'identity.view_users',
    children: [
      {
        title: 'Staff accounts',
        path: '/administration/users',
        permission: 'identity.view_users',
      },
    ],
  },
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
