import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ActivatePage } from './activate-page';
import { PortalPage } from './portal-page';

const api = vi.fn();
const post = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: (...a: unknown[]) => post(...a),
  ApiError: class extends Error {},
}));
vi.mock('@/pages/participants/capability-profile', () => ({
  CapabilityProfile: () => <div>profile editor</div>,
}));

const wrap = (ui: React.ReactNode) =>
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );

describe('ActivatePage', () => {
  beforeEach(() => {
    post.mockReset();
    window.location.hash = '';
  });

  it('refuses a link with no token', () => {
    wrap(<ActivatePage />);
    expect(screen.getByRole('alert').textContent).toMatch(/not complete/);
  });

  it('checks the token then lets the youth set a password', async () => {
    window.location.hash = '#token=abc';
    post.mockResolvedValue(undefined);
    wrap(<ActivatePage />);
    const pw = await screen.findByLabelText('Choose a password');
    fireEvent.change(pw, { target: { value: 'a-long-password-1' } });
    fireEvent.change(screen.getByLabelText('Type it again'), {
      target: { value: 'a-long-password-1' },
    });
    fireEvent.click(screen.getByText('Set password'));
    expect(await screen.findByText(/password is set/)).toBeTruthy();
    expect(post).toHaveBeenCalledWith('/youth/activate', {
      token: 'abc',
      password: 'a-long-password-1',
    });
  });
});

describe('PortalPage', () => {
  beforeEach(() => api.mockReset());

  it('shows the consent notice before any profile', async () => {
    api.mockResolvedValue({
      name: 'Amina',
      consent: { version: 'v1', text: 'Notice text', given: false },
    });
    wrap(<PortalPage />);
    expect(await screen.findByText('Notice text')).toBeTruthy();
    expect(screen.queryByText('profile editor')).toBeNull();
  });

  it('shows the profile once consent is given', async () => {
    api.mockResolvedValue({
      name: 'Amina',
      consent: { version: 'v1', text: 'Notice text', given: true },
    });
    wrap(<PortalPage />);
    expect(await screen.findByText('profile editor')).toBeTruthy();
  });
});
