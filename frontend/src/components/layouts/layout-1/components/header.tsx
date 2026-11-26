import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { LogOut, Menu, UserRound } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router';
import { generalSettings } from '@/config/general.config';
import { cn } from '@/lib/utils';
import { useIsMobile } from '@/hooks/use-mobile';
import { useScrollPosition } from '@/hooks/use-scroll-position';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { SidebarMenu } from './sidebar-menu';

/** The CAP-YEI mark with the product name: "PI 360" in the bar, the full name in the menu. */
function Brand({ full = false }: { full?: boolean }) {
  return (
    <Link
      to="/"
      aria-label={`${full ? generalSettings.appName : 'PI 360'}, home`}
      className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-md pe-1 font-semibold text-mono"
    >
      <img
        src="/media/app/cap-mark.png"
        alt=""
        aria-hidden
        className="size-8 shrink-0 object-contain"
      />
      {full ? (
        <span className="text-sm leading-tight">{generalSettings.appName}</span>
      ) : (
        <span className="text-base tracking-tight">
          PI <span className="text-primary">360</span>
        </span>
      )}
    </Link>
  );
}

// The kit's search, notifications, chat, apps and user menus are not shipped
// in v9.5.0 and are not in the PI 360 design. The user menu arrives with the
// auth adapter (T-143).
export function Header() {
  const [isSidebarSheetOpen, setIsSidebarSheetOpen] = useState(false);
  const { pathname } = useLocation();
  const mobileMode = useIsMobile();
  const headerSticky = useScrollPosition() > 0;
  const { me, logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    setIsSidebarSheetOpen(false);
  }, [pathname]);

  return (
    <header
      className={cn(
        'header fixed top-0 z-10 start-0 flex items-stretch shrink-0 border-b border-transparent bg-background end-0 pe-[var(--removed-body-scroll-bar-size,0px)]',
        'max-lg:border-border max-lg:shadow-xs',
        headerSticky && 'border-b border-border',
      )}
    >
      <div className="container-fluid flex justify-between items-center lg:gap-4">
        <div className="flex lg:hidden items-center gap-1.5">
          {mobileMode && (
            <Sheet
              open={isSidebarSheetOpen}
              onOpenChange={setIsSidebarSheetOpen}
            >
              <SheetTrigger asChild>
                <Button
                  variant="outline"
                  mode="icon"
                  aria-label="Open menu"
                  className="-ms-1 text-foreground"
                >
                  <Menu className="size-5" />
                </Button>
              </SheetTrigger>
              <SheetContent
                className="p-0 gap-0 w-[275px]"
                side="left"
                close={false}
              >
                <SheetHeader className="space-y-0 border-b border-border p-4">
                  <SheetTitle className="sr-only">Menu</SheetTitle>
                  <Brand full />
                </SheetHeader>
                <SheetBody className="p-0 overflow-y-auto">
                  <SidebarMenu />
                </SheetBody>
              </SheetContent>
            </Sheet>
          )}
          <Brand />
        </div>

        <div className="ms-auto flex items-center gap-3 text-sm">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="gap-2 px-2 max-sm:min-w-11">
                <Avatar
                  aria-hidden="true"
                  className="size-8 ring-2 ring-primary/15"
                >
                  <AvatarFallback className="bg-primary/10 text-xs font-medium uppercase text-primary">
                    {me?.username?.slice(0, 2)}
                  </AvatarFallback>
                </Avatar>
                <span className="text-foreground max-sm:sr-only">
                  {me?.username}
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="space-y-0.5">
                <div className="text-sm font-medium text-foreground">
                  {me?.username}
                </div>
                <div className="text-xs font-normal capitalize text-muted-foreground">
                  {me?.roles?.length ? me.roles.join(', ') : 'No role assigned'}
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => navigate('/account')}>
                <UserRound /> My account
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() =>
                  void logout().then(() =>
                    navigate('/login', { replace: true }),
                  )
                }
              >
                <LogOut /> Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
