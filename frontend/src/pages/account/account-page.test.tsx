import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChangePasswordForm } from './account-page';

const toast = vi.hoisted(() => ({ success: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

function reply(status: number, body?: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

function fill(current: string, next: string, again: string) {
  const type = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  type('Current password', current);
  type('New password', next);
  type('Type the new password again', again);
  fireEvent.click(screen.getByRole('button', { name: 'Change password' }));
}

afterEach(() => {
  vi.restoreAllMocks();
  toast.success.mockClear();
});

describe('ChangePasswordForm', () => {
  it('will not send when the two new passwords differ', async () => {
    const fetchSpy = reply(204);
    render(<ChangePasswordForm />);
    fill('old-password-1', 'new-password-12', 'new-password-13');
    expect(await screen.findByText(/two new passwords differ/i)).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('sends both passwords, clears the form and says it worked', async () => {
    const fetchSpy = reply(204);
    render(<ChangePasswordForm />);
    fill('old-password-1', 'new-password-12', 'new-password-12');
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain('/auth/password/change');
    expect(JSON.parse(String(init?.body))).toEqual({
      current_password: 'old-password-1',
      new_password: 'new-password-12',
    });
    expect(
      (screen.getByLabelText('Current password') as HTMLInputElement).value,
    ).toBe('');
  });

  it('shows the server message beside the field it names', async () => {
    reply(400, {
      code: 'validation_error',
      errors: [{ field: 'current_password', message: 'Incorrect password.' }],
    });
    render(<ChangePasswordForm />);
    fill('wrong', 'new-password-12', 'new-password-12');
    expect(await screen.findByText('Incorrect password.')).toBeTruthy();
    expect(toast.success).not.toHaveBeenCalled();
  });
});
