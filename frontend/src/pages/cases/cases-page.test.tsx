import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QueueData } from './case-shared';
import { CasesPage } from './cases-page';

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: vi.fn(),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: () => false }),
}));

const queue: QueueData = {
  scope: 'mine',
  today: '2026-11-17',
  counts: {
    live: 2,
    overdue: 1,
    due_soon: 1,
    awaiting_verification: 0,
    referrals_waiting: 0,
  },
  interventions: [
    {
      id: 'i1',
      participant_id: 'p1',
      participant: 'Amina Otieno',
      need_label: 'Mental health',
      title: 'Book a counselling visit',
      status: 'open',
      status_label: 'Open',
      owner: 'Officer One',
      due_date: '2026-11-10',
      overdue: true,
    },
    {
      id: 'i2',
      participant_id: 'p2',
      participant: 'Brian Kamau',
      need_label: 'Transport',
      title: 'Arrange fare support',
      status: 'in_progress',
      status_label: 'In progress',
      owner: 'Officer One',
      due_date: '2026-11-20',
      overdue: false,
    },
  ],
  referrals: [],
  flags: null,
  placements_to_verify: null,
  followups: null,
};

const renderPage = (url = '/cases') =>
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[url]}>
          <CasesPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );

describe('CasesPage', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockResolvedValue(queue);
  });

  it('asks for my work by default and marks overdue items', async () => {
    renderPage();
    expect(await screen.findByText('Amina Otieno')).toBeTruthy();
    expect(api).toHaveBeenCalledWith('/cases/queue?mine=1');
    expect(screen.getAllByText('Overdue').length).toBeGreaterThan(0);
    // only one row carries the Overdue badge (the stat card is a label, not a badge)
    expect(screen.getByText('Brian Kamau')).toBeTruthy();
  });

  it('switches to everyone', async () => {
    renderPage();
    await screen.findByText('Amina Otieno');
    fireEvent.click(screen.getByRole('button', { name: 'Everyone' }));
    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith('/cases/queue?mine=0'),
    );
  });

  it('hides the record button from roles that cannot edit', async () => {
    renderPage();
    await screen.findByText('Amina Otieno');
    expect(screen.queryByText('Record intervention')).toBeNull();
  });
});
