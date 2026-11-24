import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  RegistrationsPage,
  type Registration,
  type RegistrationQueue,
} from './registrations-page';

const api = vi.fn();
const post = vi.fn();
let permissions: string[] = [];
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: (...a: unknown[]) => post(...a),
  ApiError: class extends Error {
    status = 0;
  },
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: (p: string) => permissions.includes(p) }),
}));

const reg = (over: Partial<Registration> = {}): Registration => ({
  id: 'r1',
  name: 'Test Person',
  date_of_birth: '2003-05-01',
  email: 'test.person@example.org',
  phone: '',
  programme_code: '',
  enrollment_no: '',
  email_verified: false,
  phone_verified: false,
  status: 'pending_verification',
  status_label: 'Waiting for verification',
  possible_duplicate: false,
  reviewed_by: '',
  decision_reason: '',
  created_at: '2026-11-24T08:00:00Z',
  ...over,
});
const queue = (rows: Registration[]): RegistrationQueue => ({
  total: rows.length,
  counts: { pending_verification: rows.length },
  results: rows,
});

const open = () =>
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RegistrationsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );

describe('RegistrationsPage (NEW-072)', () => {
  beforeEach(() => {
    permissions = [];
    api.mockReset();
    post.mockReset();
  });

  it('lists requests and flags unverified contacts', async () => {
    api.mockResolvedValue(queue([reg({ possible_duplicate: true })]));
    open();
    expect(await screen.findByText('Test Person')).toBeTruthy();
    expect(screen.getByText(/not verified/)).toBeTruthy();
    expect(screen.getByText('Possible duplicate')).toBeTruthy();
  });

  it('asks for a reason before rejecting', async () => {
    api.mockResolvedValue(queue([reg()]));
    post.mockResolvedValue({});
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    fireEvent.change(screen.getByLabelText(/Reason for rejecting/), {
      target: { value: 'Not a CAP-YEI youth' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm rejection' }));
    await vi.waitFor(() =>
      expect(post).toHaveBeenCalledWith('/registrations/r1/reject', {
        reason: 'Not a CAP-YEI youth',
      }),
    );
  });

  it('shows Delete on rejected requests only to administrators', async () => {
    api.mockResolvedValue(
      queue([reg({ status: 'rejected', status_label: 'Rejected' })]),
    );
    open();
    await screen.findByText('Test Person');
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
  });

  it('explains when the feature is switched off', async () => {
    const err = Object.assign(
      new (await import('@/lib/api')).ApiError(404, 'Not found'),
      {
        status: 404,
      },
    );
    api.mockRejectedValue(err);
    open();
    expect(
      await screen.findByText('Self-registration is switched off'),
    ).toBeTruthy();
  });

  it('warns about similar people and links without creating', async () => {
    permissions = ['participants.edit'];
    api.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/matches')
          ? {
              matches: [
                {
                  id: 'p1',
                  name: 'Test Person',
                  status: 'active',
                  county: 'Nairobi',
                  projects: [],
                  reasons: [{ code: 'same_name', text: 'Same name' }],
                },
              ],
            }
          : queue([reg({ status: 'verified', status_label: 'Verified' })]),
      ),
    );
    post.mockResolvedValue({});
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Review' }));
    expect(await screen.findByText('Same name')).toBeTruthy();
    expect(screen.getByText(/this is a different person/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Reason for deciding/), {
      target: { value: 'Same person' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Link to Test Person' }),
    );
    await vi.waitFor(() =>
      expect(post).toHaveBeenCalledWith('/registrations/r1/link', {
        reason: 'Same person',
        participant_id: 'p1',
      }),
    );
  });
});
