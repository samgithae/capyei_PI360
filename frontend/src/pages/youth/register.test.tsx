import { fireEvent, render, screen } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RegisterPage } from './register-page';
import { RegisterVerifyPage } from './register-verify-page';

const post = vi.fn();
vi.mock('@/lib/api', () => {
  class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    // A reply of { fail: <status> } becomes a thrown ApiError, so the mock never holds a
    // rejected promise of its own.
    post: async (...a: unknown[]) => {
      const r = (await post(...a)) as { fail?: number } | undefined;
      if (r?.fail) throw new ApiError(r.fail, 'Not found');
      return r;
    },
    ApiError,
  };
});

const wrap = (ui: React.ReactNode) =>
  render(
    <HelmetProvider>
      <MemoryRouter>{ui}</MemoryRouter>
    </HelmetProvider>,
  );

const fill = () => {
  const set = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  set('First name', 'Test');
  set('Family name', 'Person');
  set('Date of birth', '2004-03-01');
  set('E-mail', 'test@example.org');
};

describe('RegisterPage', () => {
  beforeEach(() => post.mockReset());

  it('needs the consent tick before sending', async () => {
    wrap(<RegisterPage />);
    fill();
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(
      await screen.findByText('You need to agree to continue.'),
    ).toBeTruthy();
    expect(post).not.toHaveBeenCalled();
  });

  it('shows the same check-your-e-mail message after sending', async () => {
    post.mockResolvedValue({});
    wrap(<RegisterPage />);
    fill();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText(/we have sent a link/)).toBeTruthy();
    expect(post).toHaveBeenCalledWith(
      '/registrations/submit',
      expect.objectContaining({ consent: true, email: 'test@example.org' }),
    );
  });

  it('says sign-up is not open when the switch is off', async () => {
    post.mockResolvedValue({ fail: 404 });
    wrap(<RegisterPage />);
    fill();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await vi.waitFor(() =>
      expect(screen.getByText(/Sign-up is not open yet/)).toBeTruthy(),
    );
  });
});

describe('RegisterVerifyPage', () => {
  beforeEach(() => post.mockReset());

  it('confirms a good link', async () => {
    window.location.hash = '#token=abc';
    post.mockResolvedValue({});
    wrap(<RegisterVerifyPage />);
    expect(await screen.findByText(/your e-mail is confirmed/)).toBeTruthy();
    expect(post).toHaveBeenCalledWith('/registrations/verify', {
      token: 'abc',
    });
  });

  it('rejects a link with no token without calling the server', () => {
    window.location.hash = '';
    wrap(<RegisterVerifyPage />);
    expect(screen.getByText(/not complete/)).toBeTruthy();
    expect(post).not.toHaveBeenCalled();
  });
});
