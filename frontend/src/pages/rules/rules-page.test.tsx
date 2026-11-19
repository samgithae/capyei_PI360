import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RulesPage } from './rules-page';

const api = vi.fn();
const post = vi.fn();
let permissions: string[] = [];
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: (...a: unknown[]) => post(...a),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: (p: string) => permissions.includes(p) }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const RULE = {
  id: 'r1',
  module: 'matching',
  module_label: 'Matching',
  code: 'fit',
  name: 'Fit rules',
  purpose: '',
  active: { id: 'v1', number: 2, state: 'active', state_label: 'In force' },
  latest: null,
  version_count: 2,
  review: { due_on: '2026-11-01', overdue: true },
};

function show() {
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RulesPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe('RulesPage review', () => {
  beforeEach(() => {
    api.mockReset();
    post.mockReset();
    api.mockResolvedValue([RULE]);
    permissions = ['intelligence.view_rules'];
  });

  it('shows Review due but no button to someone who cannot approve', async () => {
    show();
    expect(await screen.findByText('Review due')).toBeTruthy();
    expect(
      screen.queryByRole('button', { name: /mark .* reviewed/i }),
    ).toBeNull();
  });

  it('lets an approver mark the version in force as reviewed', async () => {
    permissions = ['intelligence.view_rules', 'intelligence.approve_rules'];
    post.mockResolvedValue({});
    show();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Mark Fit rules as reviewed' }),
    );
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/rules/versions/v1/review', {}),
    );
  });

  it('shows no button when the rule is not due', async () => {
    permissions = ['intelligence.approve_rules'];
    api.mockResolvedValue([
      { ...RULE, review: { due_on: '2027-02-01', overdue: false } },
    ]);
    show();
    await screen.findByText('Fit rules');
    expect(screen.queryByText('Review due')).toBeNull();
    expect(screen.queryByRole('button', { name: /reviewed/i })).toBeNull();
  });
});
