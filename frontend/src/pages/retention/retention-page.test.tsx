import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RetentionPage, type RetentionClass } from './retention-page';

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

const cls = (over: Partial<RetentionClass> = {}): RetentionClass => ({
  code: 'import_rows',
  label: 'Imported source rows',
  description: 'The text of each spreadsheet row.',
  removes: 'the values',
  keeps: 'the counts',
  minimum_days: 30,
  period_days: null,
  basis: '',
  state: 'not_set',
  approved_by: '',
  approved_at: null,
  ...over,
});

function open(item: RetentionClass) {
  api.mockResolvedValue({ classes: [item], runs: [] });
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RetentionPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe('RetentionPage', () => {
  beforeEach(() => {
    api.mockReset();
    post.mockReset();
    permissions = ['retention.view'];
  });

  it('shows what is cleared and kept, and hides actions from read-only roles', async () => {
    open(cls());
    expect(await screen.findByText('No period set')).toBeTruthy();
    expect(screen.getByText('the values')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Set period' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Dry run' })).toBeNull();
  });

  it('validates the period and the basis before saving', async () => {
    permissions = ['retention.view', 'retention.manage'];
    open(cls());
    fireEvent.click(await screen.findByRole('button', { name: 'Set period' }));
    fireEvent.change(await screen.findByLabelText(/Keep the values/), {
      target: { value: '10' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save period' }));
    expect(await screen.findByText(/at least 30/)).toBeTruthy();
  });

  it('offers approval only when a period waits for it, and applying needs confirmation', async () => {
    permissions = ['retention.view', 'retention.manage'];
    open(
      cls({ period_days: 365, basis: 'Policy', state: 'awaiting_approval' }),
    );
    expect(await screen.findByRole('button', { name: 'Approve' })).toBeTruthy();
    expect(
      (screen.getByRole('button', { name: 'Apply now' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it('asks for confirmation before an applied run', async () => {
    permissions = ['retention.view', 'retention.manage'];
    open(
      cls({
        period_days: 365,
        basis: 'Policy',
        state: 'active',
        approved_by: 'Admin',
        approved_at: '2026-11-01T10:00:00Z',
      }),
    );
    await screen.findByText('Withdraw approval'); // the data has loaded
    fireEvent.click(screen.getByRole('button', { name: 'Apply now' }));
    expect(await screen.findByText('Clear personal values now?')).toBeTruthy();
    expect(post).not.toHaveBeenCalled();
  });
});
