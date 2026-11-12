import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DashboardPage } from './dashboard-page';

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  ApiError: class extends Error {},
}));

const wrap = (ui: React.ReactNode) =>
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );

const steps = [
  'submitted',
  'under_review',
  'interview',
  'selected',
  'placed',
].map((key) => ({ key, label: key }));

describe('DashboardPage', () => {
  beforeEach(() => api.mockReset());

  it('shows counters and the latest opportunity', async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(
        path === '/youth/me'
          ? { name: 'Amina', consent: { given: true } }
          : {
              steps,
              counts: { referred: 3, interview: 1, selected: 0, placed: 0 },
              items: [],
              latest: {
                id: 'r1',
                opportunity: 'Welder',
                employer: 'Acme',
                kind: 'job',
                location: '',
                stage: 'interview',
                stage_label: 'Interview',
                ended: false,
                referred_at: '2026-11-01',
                updated_at: '2026-11-02',
                reached: ['submitted', 'under_review', 'interview'],
              },
            },
      ),
    );
    wrap(<DashboardPage />);
    expect(await screen.findByText('Welder')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
    expect(screen.getByText('Hello, Amina')).toBeTruthy();
  });

  it('invites a youth with no referrals to keep their profile current', async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(
        path === '/youth/me'
          ? { name: 'Amina', consent: { given: true } }
          : {
              steps,
              counts: { referred: 0, interview: 0, selected: 0, placed: 0 },
              items: [],
              latest: null,
            },
      ),
    );
    wrap(<DashboardPage />);
    expect(await screen.findByText(/not been referred/)).toBeTruthy();
  });
});
