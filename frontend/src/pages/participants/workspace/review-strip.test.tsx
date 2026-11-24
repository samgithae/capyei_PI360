import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ReviewStrip } from './review-strip';
import type { Detail } from './types';

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

const detail = (state: 'none' | 'needs_review' | 'reviewed'): Detail =>
  ({
    id: 'p1',
    archived: false,
    review: {
      state,
      reason: 'self_edit',
      reason_label: 'Changed their own details',
      since: null,
    },
  }) as unknown as Detail;

const show = (d: Detail) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ReviewStrip p={d} />
    </QueryClientProvider>,
  );

describe('ReviewStrip', () => {
  beforeEach(() => {
    api.mockReset();
    post.mockReset();
    permissions = ['participants.edit'];
  });

  it('shows why a record needs review and lets an editor mark it reviewed', async () => {
    api.mockResolvedValue({ marked: 1 });
    show(detail('needs_review'));
    expect(screen.getByText('Needs review')).toBeTruthy();
    expect(screen.getByText('Changed their own details')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Mark reviewed' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm reviewed' }));
    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        '/participants/p1/review',
        expect.objectContaining({ method: 'DELETE' }),
      ),
    );
  });

  it('asks for a reason before flagging', async () => {
    show(detail('none'));
    fireEvent.click(screen.getByRole('button', { name: 'Flag for review' }));
    fireEvent.click(screen.getByRole('button', { name: 'Flag it' }));
    expect(
      await screen.findByText('Say why this record needs a look.'),
    ).toBeTruthy();
    expect(post).not.toHaveBeenCalled();
  });

  it('shows nothing to someone who cannot edit when there is no flag', () => {
    permissions = [];
    const { container } = show(detail('none'));
    expect(container.textContent).toBe('');
  });

  it('hides the action buttons from a read-only role but still shows the flag', () => {
    permissions = [];
    show(detail('needs_review'));
    expect(screen.getByText('Needs review')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Mark reviewed' })).toBeNull();
  });
});
