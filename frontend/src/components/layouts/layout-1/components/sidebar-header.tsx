import { ChevronFirst } from 'lucide-react';
import { Link } from 'react-router';
import { generalSettings } from '@/config/general.config';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useLayout } from './context';

export function SidebarHeader() {
  const { sidebarCollapse, setSidebarCollapse } = useLayout();

  const handleToggleClick = () => {
    setSidebarCollapse(!sidebarCollapse);
  };

  return (
    <div className="sidebar-header hidden lg:flex items-center relative justify-between px-3 lg:px-6 shrink-0">
      <Link
        to="/"
        className="flex items-center gap-2.5 font-semibold text-mono"
      >
        <img
          src="/media/app/cap-mark.png"
          alt=""
          aria-hidden
          className="size-8 shrink-0 object-contain"
        />
        <span className="default-logo truncate text-sm leading-tight">
          {generalSettings.appName}
        </span>
      </Link>
      <Button
        onClick={handleToggleClick}
        size="sm"
        mode="icon"
        variant="outline"
        aria-label={sidebarCollapse ? 'Expand sidebar' : 'Collapse sidebar'}
        className={cn(
          'size-7 absolute start-full top-2/4 rtl:translate-x-2/4 -translate-x-2/4 -translate-y-2/4',
          sidebarCollapse ? 'ltr:rotate-180' : 'rtl:rotate-180',
        )}
      >
        <ChevronFirst className="size-4!" />
      </Button>
    </div>
  );
}
