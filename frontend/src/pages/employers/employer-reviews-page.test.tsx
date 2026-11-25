import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { EmployerReviewsPage } from './employer-reviews-page';

const posted = vi.fn(() => Promise.resolve({}));
vi.mock('@/lib/api', () => ({
  api: () =>
    Promise.resolve({
      results: [
        {
          id: 'r1',
          employer_id: 'e1',
          employer: 'Acme',
          opened_on: '2026-11-20',
          reasons: ['Average rating is below the limit'],
          ratings_count: 3,
          status: 'open',
          outcome: '',
          outcome_label: '',
          reason: '',
          decided_by: '',
          decided_at: null,
        },
      ],
    }),
  post: (...a: unknown[]) => posted(...(a as [])),
  ApiError: class extends Error {},
}));

function show() {
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <EmployerReviewsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe('EmployerReviewsPage', () => {
  it('lists an open review and says it suspends nothing', async () => {
    show();
    expect(await screen.findByText('Acme')).toBeTruthy();
    expect(screen.getByText(/Nothing here suspends an employer/)).toBeTruthy();
  });

  it('records Monitor with the reason', async () => {
    show();
    fireEvent.click(await screen.findByText('Record a decision'));
    fireEvent.change(await screen.findByLabelText('Reason'), {
      target: { value: 'Watch next month' },
    });
    fireEvent.click(screen.getByText('Record decision'));
    await waitFor(() => expect(posted).toHaveBeenCalled());
    expect(posted).toHaveBeenCalledWith('/employers/reviews/r1/decision', {
      outcome: 'monitor',
      reason: 'Watch next month',
    });
  });
});
