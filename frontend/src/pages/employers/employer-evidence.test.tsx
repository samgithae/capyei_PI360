import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { EmployerEvidence } from './employer-evidence';

vi.mock('@/lib/api', () => ({
  api: () =>
    Promise.resolve({
      period: { from: '2026-01-01', to: '2026-11-25', days: 328 },
      minimum_referrals: 5,
      referrals_in_period: 6,
      enough: true,
      summary: 'ok',
      indicators: [],
      criteria: [
        {
          code: 'punctuality',
          label: 'Punctuality',
          source: 'Employer feedback',
          count: 2,
          average: null,
          text: '2 scores',
          status: 'insufficient',
        },
      ],
    }),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: () => true }),
}));

describe('EmployerEvidence criteria', () => {
  it('lists each criterion alone, with no average below the minimum', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <EmployerEvidence id="e1" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Punctuality')).toBeTruthy();
    expect(screen.getByText(/Insufficient evidence/)).toBeTruthy();
    expect(screen.getByText(/no overall rating/)).toBeTruthy();
  });
});
