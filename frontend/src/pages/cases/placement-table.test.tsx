import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlacementRow } from './case-shared';
import { PlacementTable } from './placement-table';

// D-081 (PI360-NEW-070): Changed employer ends the running placement and starts the next.
// All names here are made up.
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: () => true }),
}));

const api = vi.fn();
const post = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: (...a: unknown[]) => post(...a),
  ApiError: class extends Error {},
}));

const row = (over: Partial<PlacementRow> = {}): PlacementRow => ({
  id: 'pl1',
  participant_id: 'p1',
  participant: 'Test Person',
  enrollment_id: 'en1',
  employer_id: null,
  employer: 'Acme Traders',
  linked: false,
  designation: '',
  pathway: 'wage',
  pathway_label: 'Wage employment',
  status: 'placed',
  source_status: 'Employment',
  start_date: '2026-01-05',
  end_date: null,
  exit_reason: '',
  current: true,
  verified: true,
  verified_on: null,
  verification_source: '',
  verification_source_label: '',
  imported: false,
  business_activity: '',
  operational_status: '',
  operational_status_label: '',
  business_evidence: '',
  employment_type_id: null,
  employment_type: '',
  ...over,
});

function show(rows: PlacementRow[], canRecordIncome = false) {
  api.mockResolvedValue({
    results: [],
    pathways: [
      { value: 'wage', label: 'Wage employment' },
      {
        value: 'self_employment',
        label: 'Self-employment or entrepreneurship',
      },
    ],
    sources: [],
    operational_statuses: [{ value: 'operating', label: 'Operating' }],
    operational_statuses_provisional: true,
    can_record_income: canRecordIncome,
  });
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <PlacementTable rows={rows} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Changed employer', () => {
  beforeEach(() => {
    api.mockReset();
    post.mockReset();
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  it('is offered only on a running placement', () => {
    show([
      row(),
      row({
        id: 'pl2',
        participant: 'Other Person',
        current: false,
        end_date: '2025-12-01',
      }),
    ]);
    expect(
      screen.getByRole('button', { name: 'Changed employer for Test Person' }),
    ).toBeTruthy();
    expect(
      screen.queryByRole('button', {
        name: 'Changed employer for Other Person',
      }),
    ).toBeNull();
  });

  it('ends the old placement and records the new one in one request', async () => {
    post.mockResolvedValueOnce({});
    show([row()]);
    fireEvent.click(
      screen.getByRole('button', { name: 'Changed employer for Test Person' }),
    );
    fireEvent.change(await screen.findByLabelText(/old job ended on/i), {
      target: { value: '2026-10-31' },
    });
    fireEvent.change(screen.getByLabelText(/new job started on/i), {
      target: { value: '2026-11-03' },
    });
    fireEvent.change(screen.getByLabelText(/new employer or business name/i), {
      target: { value: 'Beta Ltd' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'End and record new' }));
    await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe('/placements/pl1/change-employer');
    expect(post.mock.calls[0][1]).toMatchObject({
      end_date: '2026-10-31',
      start_date: '2026-11-03',
      pathway: 'wage',
      employer_name_source: 'Beta Ltd',
    });
  });

  it('will not send a new start before the old end', async () => {
    show([row()]);
    fireEvent.click(
      screen.getByRole('button', { name: 'Changed employer for Test Person' }),
    );
    fireEvent.change(await screen.findByLabelText(/old job ended on/i), {
      target: { value: '2026-10-31' },
    });
    fireEvent.change(screen.getByLabelText(/new job started on/i), {
      target: { value: '2026-10-01' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'End and record new' }));
    expect(
      await screen.findByText(
        'The new job cannot start before the old one ended.',
      ),
    ).toBeTruthy();
    expect(post).not.toHaveBeenCalled();
  });
});

// D-080 / B27 (PI360-NEW-071): self-employment keeps its own business facts.
describe('Self-employment details', () => {
  const business = () =>
    row({
      pathway: 'self_employment',
      pathway_label: 'Self-employment or entrepreneurship',
      employer: 'Test Tailoring',
      business_activity: 'Tailoring',
      operational_status: 'operating',
      operational_status_label: 'Operating',
    });

  beforeEach(() => {
    api.mockReset();
    post.mockReset();
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  it('shows the activity and status in the table', () => {
    show([business()]);
    expect(screen.getByText('Tailoring · Operating')).toBeTruthy();
  });

  it('sends the business details without income when the grant is missing', async () => {
    post.mockResolvedValueOnce({});
    show([business()]);
    fireEvent.click(
      screen.getByRole('button', { name: 'Changed employer for Test Person' }),
    );
    fireEvent.change(await screen.findByLabelText(/old job ended on/i), {
      target: { value: '2026-10-31' },
    });
    fireEvent.change(screen.getByLabelText(/new job started on/i), {
      target: { value: '2026-11-03' },
    });
    fireEvent.change(screen.getByLabelText(/^business activity$/i), {
      target: { value: 'Mobile repairs' },
    });
    expect(screen.queryByLabelText(/monthly income/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'End and record new' }));
    await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const body = post.mock.calls[0][1];
    expect(body).toMatchObject({
      pathway: 'self_employment',
      business_activity: 'Mobile repairs',
    });
    expect(body).not.toHaveProperty('monthly_income');
  });

  it('offers income only to holders of the restricted grant', async () => {
    show([business()], true);
    fireEvent.click(
      screen.getByRole('button', { name: 'Changed employer for Test Person' }),
    );
    expect(await screen.findByLabelText(/monthly income/i)).toBeTruthy();
    expect(screen.getByText(/waiting for CAP-YEI to confirm/i)).toBeTruthy();
  });
});
