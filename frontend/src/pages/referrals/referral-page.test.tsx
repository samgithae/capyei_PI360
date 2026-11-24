import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import { ReferralPage } from './referral-page';

let allowed = ['placements.edit'];
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: (p?: string) => !p || allowed.includes(p) }),
}));

const api = vi.fn();
const post = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: (...a: unknown[]) => post(...a),
  ApiError: class extends Error {
    constructor(
      public status = 0,
      message = '',
      public errors: { field: string; message: string; code: string }[] = [],
    ) {
      super(message);
    }
  },
}));

const detail = (stage: string) => ({
  id: 'r1',
  participant_id: 'p1',
  participant: 'John Mwangi Kamau',
  opportunity_id: 'o1',
  opportunity: 'Waitstaff',
  employer: 'Java House - Ruiru',
  employer_id: 'e1',
  origin: 'officer',
  stage,
  stage_label: stage,
  reason: '',
  reason_id: null,
  reason_note: '',
  assigned_to: '',
  assigned_to_id: null,
  referred_at: null,
  closed_at: null,
  interview_at: null,
  interview_place: '',
  interview_note: '',
  created_by: '',
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  next_stages: [],
  unsuccessful: [],
  history: [],
  can: { edit: true, reopen: false, reassign: false, view_profile: false },
});

function show(stage: string) {
  api.mockImplementation((path: string) =>
    Promise.resolve(
      path.endsWith('/history')
        ? []
        : path.startsWith('/employers') || path.startsWith('/placements')
          ? {
              results: [],
              pathways: [{ value: 'wage', label: 'Wage employment' }],
              sources: [],
            }
          : detail(stage),
    ),
  );
  return render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/referrals/r1']}>
          <Routes>
            <Route path="/referrals/:id" element={<ReferralPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe('Record placement from a referral', () => {
  beforeEach(() => {
    api.mockReset();
    post.mockReset();
    // cmdk (the choice lists) measures with ResizeObserver, which jsdom lacks.
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    Element.prototype.scrollIntoView = () => {};
    allowed = ['placements.edit'];
  });

  it('opens the placement form with the youth, employer and role filled in', async () => {
    show('selected');
    fireEvent.click(
      await screen.findByRole('button', { name: /record placement/i }),
    );
    expect(await screen.findByText('Record a placement')).toBeTruthy();
    expect(screen.getAllByText('John Mwangi Kamau').length).toBeGreaterThan(1);
    expect(screen.getByDisplayValue('Waitstaff')).toBeTruthy();
    expect(screen.getAllByText('Java House - Ruiru').length).toBeGreaterThan(0);
  });

  it('is not offered before the youth is selected', async () => {
    show('under_review');
    await screen.findAllByText('John Mwangi Kamau');
    expect(
      screen.queryByRole('button', { name: /record placement/i }),
    ).toBeNull();
  });

  it('is not offered to someone who cannot edit placements', async () => {
    allowed = [];
    show('selected');
    await screen.findAllByText('John Mwangi Kamau');
    expect(
      screen.queryByRole('button', { name: /record placement/i }),
    ).toBeNull();
  });

  it('shows the refusal for a second running placement, with what to do instead', async () => {
    const refusal =
      'This youth already has a running placement with Test Employer, since 01 Mar 2026. End it first, or use Changed employer.';
    post.mockRejectedValueOnce(
      new ApiError(409, refusal, [
        { field: '', message: refusal, code: 'active_placement' },
      ]),
    );
    show('selected');
    fireEvent.click(
      await screen.findByRole('button', { name: /record placement/i }),
    );
    await screen.findByText('Record a placement');
    fireEvent.click(screen.getByRole('combobox', { name: 'Choose pathway' }));
    fireEvent.click(await screen.findByText('Wage employment'));
    fireEvent.change(screen.getByLabelText(/start date/i), {
      target: { value: '2026-11-19' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));

    expect(await screen.findByText(refusal)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /record anyway/i })).toBeNull();
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][1]).not.toHaveProperty('confirm_duplicate');
  });
});
