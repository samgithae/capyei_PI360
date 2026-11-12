import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SuggestedYouth } from './suggested-youth';

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  ApiError: class extends Error {},
}));

function show(props: { positions?: number; canRefer?: boolean } = {}) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <SuggestedYouth id="o1" {...props} />
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
          met: 1,
          checked: 1,
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

  const two = {
    available: true,
    rule: { version: 2 },
    counts: { eligible: 2, no_data: 0 },
    truncated: false,
    weights_pending: true,
    requirements: 2,
    suggestions: ['A Strong', 'B Weak'].map((name, i) => ({
      participant_id: `p${i}`,
      name,
      group: 'eligible',
      score: null,
      met: 2 - i,
      checked: 2,
      preferred_met: 1 - i,
      preferred_total: 1,
      coverage: null,
      checks: [
        {
          label: 'Skill: Welding',
          mandatory: true,
          outcome: i ? 'fail' : 'pass',
          note: '',
          source: null,
          verified: false,
        },
      ],
      missing: [],
      not_checked: [],
    })),
  };

  it('numbers the youth, shows reasons inline and says why there is no percentage', async () => {
    api.mockResolvedValue(two);
    show();
    expect(await screen.findByText('A Strong')).toBeTruthy();
    expect(screen.getByText('Meets 2 of 2')).toBeTruthy();
    expect(screen.getByText('Preferred: 1 of 1')).toBeTruthy();
    expect(screen.getAllByText(/Skill: Welding/).length).toBe(2);
    expect(screen.getByText(/percentage fit is not shown/i)).toBeTruthy();
    expect(screen.getByText('1.')).toBeTruthy();
  });

  it('selects the top N for the positions on offer', async () => {
    api.mockResolvedValue(two);
    show({ positions: 1, canRefer: true });
    await screen.findByText('A Strong');
    fireEvent.click(screen.getByRole('button', { name: 'Select top 1' }));
    expect(
      screen.getByRole('button', { name: 'Refer selected (1)' }),
    ).toBeTruthy();
  });

  it('offers no tick boxes when referring is not allowed', async () => {
    api.mockResolvedValue(two);
    show({ canRefer: false });
    await screen.findByText('A Strong');
    expect(screen.queryByRole('button', { name: /Refer selected/ })).toBeNull();
  });

  it('refreshes the suggestions on demand', async () => {
    api.mockResolvedValue(two);
    show();
    await screen.findByText('A Strong');
    const calls = api.mock.calls.length;
    fireEvent.click(
      screen.getByRole('button', { name: /Refresh suggestions/ }),
    );
    await screen.findByText('A Strong');
    expect(api.mock.calls.length).toBeGreaterThan(calls);
  });
});
