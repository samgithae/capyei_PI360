import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConsentCard } from './consent-card';
import type { Detail } from './types';

const api = vi.fn();
let permissions: string[] = [];
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: (p: string) => permissions.includes(p) }),
}));

function show(consent: Partial<Detail['consent']> = {}) {
  const p = {
    id: 'p1',
    consent: {
      status: 'not_recorded',
      label: 'Not recorded',
      notice_version: '',
      recorded_on: null,
      ...consent,
    },
  } as Detail;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ConsentCard p={p} consent={p.consent!} />
    </QueryClientProvider>,
  );
}

describe('ConsentCard', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockResolvedValue({});
    permissions = ['participants.edit'];
  });

  it('flags a youth whose consent is not recorded', () => {
    show();
    expect(screen.getByText(/has not been recorded/i)).toBeTruthy();
  });

  it('shows the notice version and date once recorded', () => {
    show({
      status: 'given',
      label: 'Given',
      notice_version: 'v1',
      recorded_on: '2026-11-01',
    });
    expect(screen.getByText('Given')).toBeTruthy();
    expect(screen.getByText(/Notice version v1/)).toBeTruthy();
    expect(screen.queryByText(/has not been recorded/i)).toBeNull();
  });

  it('hides the button without the edit permission', () => {
    permissions = [];
    show();
    expect(screen.queryByRole('button', { name: 'Record consent' })).toBeNull();
  });

  it('asks for the notice version before saving a decision', async () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Record consent' }));
    fireEvent.change(await screen.findByLabelText('Consent status'), {
      target: { value: 'given' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByRole('alert').textContent).toMatch(/notice version/i);
    expect(api).not.toHaveBeenCalled();
  });

  it('saves the status, version and date', async () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Record consent' }));
    fireEvent.change(await screen.findByLabelText('Consent status'), {
      target: { value: 'given' },
    });
    fireEvent.change(screen.getByLabelText('Privacy notice version'), {
      target: { value: ' v1 ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api).toHaveBeenCalled());
    const [path, init] = api.mock.calls[0];
    expect(path).toBe('/participants/p1/consent');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toEqual({
      status: 'given',
      notice_version: 'v1',
    });
  });
});
