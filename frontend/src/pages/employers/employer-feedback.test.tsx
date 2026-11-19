import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EmployerFeedback } from './employer-feedback';

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

const ENTRY = {
  id: 'f1',
  party: 'employer',
  party_label: 'The employer',
  source: 'call',
  source_label: 'Phone call',
  rating: 4,
  note: 'Happy with the intake',
  given_on: '2026-11-10',
  recorded_by: 'officer',
};

function show() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <EmployerFeedback id="e1" />
    </QueryClientProvider>,
  );
}

describe('EmployerFeedback', () => {
  beforeEach(() => {
    api.mockReset();
    post.mockReset();
    api.mockResolvedValue({ results: [ENTRY] });
    permissions = ['employers.view'];
  });

  it('lists entries with their source and hides the add button without edit', async () => {
    show();
    expect(await screen.findByText(/4 out of 5/)).toBeTruthy();
    expect(screen.getByText(/Phone call/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Add feedback' })).toBeNull();
  });

  it('sends the source, rating and date when an officer adds feedback', async () => {
    permissions = ['employers.view', 'employers.edit'];
    post.mockResolvedValue({});
    show();
    await screen.findByText(/4 out of 5/);
    fireEvent.click(screen.getByRole('button', { name: 'Add feedback' }));
    fireEvent.change(screen.getByLabelText('Source'), {
      target: { value: 'visit' },
    });
    fireEvent.change(screen.getByLabelText(/Rating/), {
      target: { value: '2' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    const [path, body] = post.mock.calls[0];
    expect(path).toBe('/employers/e1/feedback');
    expect(body).toMatchObject({
      source: 'visit',
      rating: 2,
      party: 'employer',
    });
  });
});
