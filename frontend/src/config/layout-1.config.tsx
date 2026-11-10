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
// by the user's permissions once the auth adapter lands (T-142).
export const MENU_SIDEBAR: MenuConfig = [
  { title: 'Overview', icon: LayoutDashboard, path: '/' },
  { heading: 'Participants' },
  { title: 'Youth', icon: Users, path: '/youth' },
  { title: 'Support priority', icon: LifeBuoy, path: '/support' },
  { heading: 'Placement' },
  { title: 'Opportunities', icon: Briefcase, path: '/opportunities' },
  { title: 'Employers', icon: Building2, path: '/employers' },
  { title: 'Referrals and cases', icon: ClipboardList, path: '/referrals' },
  { heading: 'Insight' },
  { title: 'Reports', icon: BarChart3, path: '/reports' },
  { heading: 'System' },
  { title: 'Administration', icon: Settings, path: '/admin' },
];
