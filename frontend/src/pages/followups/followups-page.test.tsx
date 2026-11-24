import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FollowUpPage } from './followup-page';
import type {
  FollowUpDetail,
  FollowUpRow,
  FollowUpSummary,
  FollowUpPage as Page,
  ScheduleStep,
} from './followup-shared';
import { FollowUpsPage } from './followups-page';
import { FollowUpSchedulePage } from './schedule-page';

const api = vi.fn();
let permissions: string[] = [];
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: vi.fn(),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: (p: string) => permissions.includes(p) }),
}));

const row = (over: Partial<FollowUpRow> = {}): FollowUpRow => ({
  id: 'f1',
  participant_id: 'p1',
  participant: 'Amina Otieno',
  placement_id: 'pl1',
  employer: 'Acme Ltd',
  designation: 'Cashier',
  placement_start: '2026-08-01',
  placement_ended: false,
  kind: 'early',
  kind_label: 'Early follow-up',
  label: '30 days',
  due_date: '2026-08-31',
  status: 'open',
  status_label: 'Open',
  overdue: true,
  assigned_to_id: 1,
  assigned_to: 'Officer One',
  next_action: 'Call again',
  next_action_date: '2026-11-20',
  attempts: 1,
  ...over,
});

const summary: FollowUpSummary = {
  open: 2,
  overdue: 1,
  due_soon: 1,
  done: 3,
  unreachable: 0,
  by_kind: {
    early: { label: 'Early follow-up', open: 1, done: 2 },
    tracer: { label: 'Tracer follow-up', open: 1, done: 1 },
  },
};

const page: Page = {
  total: 2,
  page_size: 25,
  results: [
    row(),
    row({
      id: 'f2',
      participant: 'Brian Kamau',
      label: '6 months',
      kind: 'tracer',
      kind_label: 'Tracer follow-up',
      overdue: false,
      next_action: '',
      next_action_date: null,
    }),
  ],
};

const detail: FollowUpDetail = {
  ...row(),
  response_note: '',
  still_employed: null,
  outcome: '',
  outcome_label: '',
  leaving_reason_id: null,
  leaving_reason: '',
  left_on: null,
  observations: '',
  new_placement_id: null,
  evidence_source: '',
  evidence_source_label: '',
  closed_at: null,
  closed_by: '',
  attempt_list: [
    {
      id: 'a1',
      method: 'phone',
      method_label: 'Phone call',
      reached: false,
      made_on: '2026-11-10',
      note: 'Phone was off',
      made_by: 'Officer One',
    },
  ],
  can: { work: true, assign: false },
};

const steps: ScheduleStep[] = [
  {
    id: 's1',
    kind: 'early',
    kind_label: 'Early follow-up',
    label: '30 days',
    offset_days: 30,
    active: true,
  },
  {
    id: 's2',
    kind: 'tracer',
    kind_label: 'Tracer follow-up',
    label: '6 months',
    offset_days: 183,
    active: false,
  },
];

const wrap = (ui: React.ReactNode, url: string) =>
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );

describe('FollowUpsPage', () => {
  beforeEach(() => {
    permissions = [];
    api.mockReset();
    api.mockImplementation((path: string) =>
      Promise.resolve(path.startsWith('/followups/summary') ? summary : page),
    );
  });

  it('lists check-ins, marks overdue and shows early and tracer counts', async () => {
    wrap(<FollowUpsPage />, '/followups');
    expect(await screen.findByText('Amina Otieno')).toBeTruthy();
    expect(screen.getByText('Brian Kamau')).toBeTruthy();
    expect(screen.getAllByText('Overdue').length).toBeGreaterThan(1);
    expect(await screen.findByText('Early follow-up: open')).toBeTruthy();
    expect(screen.getByText('Tracer follow-up: done')).toBeTruthy();
  });

  it('switches to my work', async () => {
    wrap(<FollowUpsPage />, '/followups');
    await screen.findByText('Amina Otieno');
    fireEvent.click(screen.getByRole('button', { name: 'Mine' }));
    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        expect.stringContaining('/followups?mine=1'),
      ),
    );
  });

  it('shows the schedule link only to people who can view configuration', async () => {
    wrap(<FollowUpsPage />, '/followups');
    await screen.findByText('Amina Otieno');
    expect(screen.queryByRole('link', { name: 'Schedule' })).toBeNull();
  });

  it('shows a friendly empty state', async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(
        path.startsWith('/followups/summary')
          ? summary
          : { total: 0, page_size: 25, results: [] },
      ),
    );
    wrap(<FollowUpsPage />, '/followups');
    expect(await screen.findByText('No follow-ups to do')).toBeTruthy();
  });
});

describe('FollowUpPage', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockImplementation((path: string) =>
      Promise.resolve(path.endsWith('/history') ? [] : detail),
    );
  });

  const open = () =>
    wrap(
      <Routes>
        <Route path="/followups/:id" element={<FollowUpPage />} />
      </Routes>,
      '/followups/f1',
    );

  it('shows attempts and the work buttons for someone who can work it', async () => {
    open();
    expect(await screen.findByText('Phone was off')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Log an attempt' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Reassign' })).toBeNull();
  });

  it('hides the work buttons from read-only roles', async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/history')
          ? []
          : { ...detail, can: { work: false, assign: false } },
      ),
    );
    open();
    await screen.findByText('Phone was off');
    expect(screen.queryByRole('button', { name: 'Log an attempt' })).toBeNull();
  });

  it('opens the attempt form with a save button', async () => {
    open();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Log an attempt' }),
    );
    expect(
      await screen.findByRole('button', { name: 'Save attempt' }),
    ).toBeTruthy();
    expect(screen.getByLabelText(/Next action \(optional\)/)).toBeTruthy();
  });
});

describe('FollowUpPage outcome (NEW-034)', () => {
  beforeEach(() => {
    api.mockReset();
  });

  const open = () =>
    wrap(
      <Routes>
        <Route path="/followups/:id" element={<FollowUpPage />} />
      </Routes>,
      '/followups/f1',
    );

  it('asks what the youth is doing now before closing the check-in', async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/history')
          ? []
          : path.endsWith('/options')
            ? { methods: [], sources: [], outcomes: [], leaving_reasons: [] }
            : detail,
      ),
    );
    open();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Record the response' }),
    );
    expect(await screen.findByText('What are they doing now?')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Complete check-in' }));
    expect(
      await screen.findByText('Say what the youth is doing now.'),
    ).toBeTruthy();
  });

  it('shows the recorded outcome, reason and observations', async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/history')
          ? []
          : {
              ...detail,
              status: 'done',
              status_label: 'Done',
              outcome: 'left_employment',
              outcome_label: 'No longer working',
              leaving_reason: 'Contract completed',
              left_on: '2026-10-31',
              observations: 'Looking for similar work',
            },
      ),
    );
    open();
    expect(await screen.findByText('No longer working')).toBeTruthy();
    expect(screen.getByText('Contract completed')).toBeTruthy();
    expect(screen.getByText('Looking for similar work')).toBeTruthy();
    expect(screen.queryByText('Still in the placement')).toBeNull();
  });
});

describe('FollowUpSchedulePage', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockResolvedValue({ results: steps });
  });

  it('lists the steps and says changes affect new placements only', async () => {
    permissions = ['config.view'];
    wrap(<FollowUpSchedulePage />, '/administration/followup-schedule');
    expect((await screen.findAllByText('30 days')).length).toBeGreaterThan(0);
    expect(screen.getByText('Paused')).toBeTruthy();
    expect(
      screen.getByText(/affects placements recorded after it/),
    ).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Add step' })).toBeNull();
  });

  it('lets people with manage permission add a step', async () => {
    permissions = ['config.view', 'config.manage'];
    wrap(<FollowUpSchedulePage />, '/administration/followup-schedule');
    fireEvent.click(await screen.findByRole('button', { name: 'Add step' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save step' }));
    expect(await screen.findByText('Give the step a name.')).toBeTruthy();
  });
});
