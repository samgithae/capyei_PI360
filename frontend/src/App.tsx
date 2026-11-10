import { AuthProvider } from '@/auth/auth-context';
import { AppRouting } from '@/routing/app-routing';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from 'next-themes';
import { HelmetProvider } from 'react-helmet-async';
import { BrowserRouter } from 'react-router';
import { LoadingBarContainer } from 'react-top-loading-bar';
import { Toaster } from '@/components/ui/sonner';

const { BASE_URL } = import.meta.env;
const queryClient = new QueryClient();

export function App() {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      storageKey="pi360-theme"
      enableSystem
      disableTransitionOnChange
      enableColorScheme
    >
      <QueryClientProvider client={queryClient}>
        <HelmetProvider>
          <LoadingBarContainer>
            <BrowserRouter basename={BASE_URL}>
              <Toaster />
              <AuthProvider>
                <AppRouting />
              </AuthProvider>
            </BrowserRouter>
          </LoadingBarContainer>
        </HelmetProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
