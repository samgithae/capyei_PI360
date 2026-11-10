import { useEffect } from 'react';
import { Outlet } from 'react-router';
import { useIsMobile } from '@/hooks/use-mobile';
import { useLayout } from './context';
import { Footer } from './footer';
import { Header } from './header';
import { Sidebar } from './sidebar';

export function Main() {
  const isMobile = useIsMobile();
  const { sidebarCollapse } = useLayout();

  useEffect(() => {
    document.body.classList.toggle('sidebar-collapse', sidebarCollapse);
  }, [sidebarCollapse]);

  useEffect(() => {
    const bodyClass = document.body.classList;
    bodyClass.add('demo1', 'sidebar-fixed', 'header-fixed');
    const timer = setTimeout(() => bodyClass.add('layout-initialized'), 1000);
    return () => {
      bodyClass.remove(
        'demo1',
        'sidebar-fixed',
        'sidebar-collapse',
        'header-fixed',
        'layout-initialized',
      );
      clearTimeout(timer);
    };
  }, []);

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:start-2 focus:z-50 focus:bg-background focus:p-2"
      >
        Skip to main content
      </a>
      {!isMobile && <Sidebar />}

      <div className="wrapper flex grow flex-col">
        <Header />

        <main id="main-content" className="grow pt-5" tabIndex={-1}>
          <Outlet />
        </main>

        <Footer />
      </div>
    </>
  );
}
