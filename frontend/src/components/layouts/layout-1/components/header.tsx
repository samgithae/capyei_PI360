import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { LogOut, Menu } from 'lucide-react';
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
        headerSticky && 'border-b border-border',
      )}
    >
      <div className="container-fluid flex justify-between items-center lg:gap-4">
        <div className="flex lg:hidden items-center gap-2.5">
          <Link to="/" className="shrink-0 font-semibold text-mono">
            {generalSettings.shortName}
          </Link>
          {mobileMode && (
            <Sheet
              open={isSidebarSheetOpen}
              onOpenChange={setIsSidebarSheetOpen}
            >
              <SheetTrigger asChild>
                <Button variant="ghost" mode="icon" aria-label="Open menu">
                  <Menu className="text-muted-foreground/70" />
                </Button>
              </SheetTrigger>
              <SheetContent
                className="p-0 gap-0 w-[275px]"
                side="left"
                close={false}
              >
                <SheetHeader className="p-0 space-y-0">
                  <SheetTitle className="sr-only">Menu</SheetTitle>
                </SheetHeader>
                <SheetBody className="p-0 overflow-y-auto">
                  <SidebarMenu />
                </SheetBody>
              </SheetContent>
            </Sheet>
          )}
        </div>

        <div className="ms-auto flex items-center gap-3 text-sm">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="gap-2 px-2"
                aria-label="Account menu"
              >
                <Avatar className="size-7">
                  <AvatarFallback className="bg-primary/10 text-xs font-medium uppercase text-primary">
                    {me?.username?.slice(0, 2)}
                  </AvatarFallback>
                </Avatar>
                <span className="hidden sm:inline text-foreground">
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
