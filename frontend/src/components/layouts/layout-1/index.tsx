import { Helmet } from 'react-helmet-async';
import { generalSettings } from '@/config/general.config';
import { LayoutProvider } from './components/context';
import { Main } from './components/main';

export function Layout1() {
  return (
    <>
      <Helmet>
        <title>{generalSettings.appName}</title>
      </Helmet>
      <LayoutProvider>
        <Main />
      </LayoutProvider>
    </>
  );
}
