import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from './auth-context';

let signedIn = true;
vi.mock('@/lib/api', () => ({
  UNAUTHENTICATED_EVENT: 'pi360:unauthenticated',
  api: vi.fn(async () =>
    signedIn
      ? {
          authenticated: true,
          username: 'dev',
          permissions: ['employers.edit'],
        }
      : { authenticated: false },
  ),
  post: vi.fn(async () => {
    signedIn = false;
  }),
}));

function Probe() {
  const { authenticated, can, logout } = useAuth();
  return (
    <div>
      <span>{authenticated ? 'in' : 'out'}</span>
      <span>{can('employers.edit') ? 'can-edit' : 'cannot-edit'}</span>
      <button onClick={() => void logout()}>sign out</button>
    </div>
  );
}

function setup() {
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    signedIn = true;
  });

  it('exposes permissions from /me', async () => {
    setup();
    expect(await screen.findByText('in')).toBeInTheDocument();
    expect(screen.getByText('can-edit')).toBeInTheDocument();
  });

  // Regression: logout used queryClient.clear(), which detached the mounted `me` observer,
  // so the UI stayed "signed in" until a reload.
  it('flips to signed out in the mounted UI after logout', async () => {
    setup();
    await screen.findByText('in');
    await act(async () => screen.getByText('sign out').click());
    await waitFor(() => expect(screen.getByText('out')).toBeInTheDocument());
    expect(screen.getByText('cannot-edit')).toBeInTheDocument();
  });
});
