import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SuggestedYouth } from './suggested-youth';

const api = vi.fn();
vi.mock('@/lib/api', () => ({ api: (...a: unknown[]) => api(...a) }));

function show() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <SuggestedYouth id="o1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SuggestedYouth', () => {
  beforeEach(() => api.mockReset());

  it('explains why there are no suggestions when no rule is active', async () => {
    api.mockResolvedValue({ available: false, reason: 'No active rule.' });
    show();
    expect(await screen.findByText('No active rule.')).toBeTruthy();
  });

  it('lists a suggested youth with the group label', async () => {
    api.mockResolvedValue({
      available: true,
      rule: { version: 2 },
      counts: { eligible: 1, no_data: 0 },
      truncated: false,
      suggestions: [
        {
          participant_id: 'p1',
          name: 'Test Youth',
          group: 'eligible',
          score: 80,
          coverage: 1,
          checks: [],
          missing: [],
          not_checked: [],
        },
      ],
    });
    show();
    expect(await screen.findByText('Test Youth')).toBeTruthy();
    expect(screen.getAllByText('Eligible').length).toBeGreaterThan(0);
  });
});
