import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisabilityCard } from './disability-card';

const api = vi.fn();
let permissions: string[] = [];
vi.mock('@/lib/api', () => {
  class ApiError extends Error {
    status: number;
    constructor(status: number, message = '') {
      super(message);
      this.status = status;
    }
  }
  return { api: (...a: unknown[]) => api(...a), ApiError };
});
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: (p: string) => permissions.includes(p) }),
}));

// jsdom has neither, and the searchable select (cmdk) measures and scrolls with them.
class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', FakeResizeObserver);
Element.prototype.scrollIntoView = () => {};

const wrap = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DisabilityCard participantId="p1" />
    </QueryClientProvider>,
  );

describe('DisabilityCard', () => {
  beforeEach(() => {
    api.mockReset();
    permissions = [];
  });

  it('never asks the server without the permission', () => {
    wrap();
    expect(api).not.toHaveBeenCalled();
    expect(screen.queryByText('Disability')).toBeNull();
  });

  it('is hidden when the server switch is off (404)', async () => {
    permissions = ['participants.view_disability'];
    const { ApiError } = await import('@/lib/api');
    api.mockRejectedValue(new ApiError(404, 'Not found'));
    wrap();
    await vi.waitFor(() => expect(api).toHaveBeenCalled());
    expect(screen.queryByText('Disability')).toBeNull();
  });

  it('shows Not recorded, offers only Yes/No, and saves', async () => {
    permissions = ['participants.view_disability'];
    api.mockImplementation((_p: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'PUT'
          ? { disability: 'no', description: '', recorded_at: 'x' }
          : { disability: 'not_recorded', description: '', recorded_at: null },
      ),
    );
    wrap();
    expect(await screen.findByText('Disability')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Save answer' })).toHaveProperty(
      'disabled',
      true,
    );
    fireEvent.click(screen.getByRole('combobox', { name: /Disability/ }));
    expect(screen.queryByText(/prefer not/i)).toBeNull();
    fireEvent.click(await screen.findByText('No'));
    fireEvent.click(screen.getByRole('button', { name: 'Save answer' }));
    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        '/participants/p1/disability',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ disability: 'no', description: '' }),
        }),
      ),
    );
  });
});
