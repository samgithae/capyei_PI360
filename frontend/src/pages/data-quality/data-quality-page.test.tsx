import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DataQualityPage } from './data-quality-page';

vi.stubGlobal(
  'ResizeObserver',
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

const getApi = vi.fn();
const postApi = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => getApi(...a),
  post: (...a: unknown[]) => postApi(...a),
  postFile: vi.fn(),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: () => true }),
}));

const SUMMARY = {
  checked: 10,
  failing: 3,
  rules: [
    { code: 'no_county', label: 'No county', fix: 'Add the county', count: 2 },
    {
      code: 'age_range',
      label: 'Age out of range',
      fix: 'Check age',
      count: 1,
    },
  ],
};
const RECORDS = {
  total: 1,
  page_size: 25,
  results: [
    {
      id: 'p1',
      name: 'Ann Wanjiru',
      county: '',
      programmes: ['Go Blue'],
      enrollment_numbers: ['E1'],
      issues: [
        { code: 'no_county', label: 'No county', fix: 'Add the county' },
      ],
    },
  ],
};
const CORRECTION: {
  conflict: { value: string; batch: string; at: string } | null;
  [key: string]: unknown;
} = {
  id: 'c1',
  participant: { id: 'p1', name: 'Ann Wanjiru' },
  field_label: 'County',
  was: 'Kisumu',
  now: 'Mombasa',
  state: 'open',
  state_label: 'Open',
  enrollment_no: 'E1',
  programme: 'Go Blue',
  corrected_by: 'officer',
  corrected_at: '2026-11-19T10:00:00Z',
  conflict: null,
  closed_how: '',
  closed_note: '',
};
const withConflict = {
  ...CORRECTION,
  conflict: { value: 'Nairobi', batch: 'B-7', at: '2026-11-20T10:00:00Z' },
};

function show() {
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DataQualityPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

let corrections = [CORRECTION];
beforeEach(() => {
  getApi.mockReset();
  postApi.mockReset();
  postApi.mockResolvedValue({});
  corrections = [CORRECTION];
  getApi.mockImplementation((path: string) => {
    if (path.startsWith('/participants/data-quality/records'))
      return Promise.resolve(RECORDS);
    if (path.startsWith('/participants/data-quality'))
      return Promise.resolve(SUMMARY);
    if (path.startsWith('/participants/corrections'))
      return Promise.resolve({
        total: corrections.length,
        page_size: 25,
        counts: { open: corrections.length, conflict: 0 },
        results: corrections,
      });
    return Promise.resolve({ groups: [] });
  });
});

describe('DataQualityPage', () => {
  it('lists the rules and the youth that fail them', async () => {
    show();
    expect(await screen.findByText('Ann Wanjiru')).toBeInTheDocument();
    expect(screen.getByText(/3 of 10 youth/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ann Wanjiru' })).toHaveAttribute(
      'href',
      '/youth/p1',
    );
  });

  it('narrows the list to one rule', async () => {
    show();
    await screen.findByText('Ann Wanjiru');
    fireEvent.click(screen.getByRole('button', { name: /Age out of range/ }));
    await waitFor(() =>
      expect(
        getApi.mock.calls.some((c) => String(c[0]).includes('rule=age_range')),
      ).toBe(true),
    );
  });

  it('shows the MIS corrections and confirms one with a note', async () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'MIS corrections' }));
    expect(await screen.findByText(/corrected to/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Keep my fix' })).toBeNull();
    fireEvent.change(screen.getByLabelText('Note for Ann Wanjiru'), {
      target: { value: 'Sent to MIS team' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'MIS updated' }));
    await waitFor(() =>
      expect(postApi).toHaveBeenCalledWith(
        '/participants/corrections/c1/resolve',
        {
          action: 'confirm',
          note: 'Sent to MIS team',
        },
      ),
    );
  });

  it('offers keep and accept when an import disagreed', async () => {
    corrections = [withConflict];
    show();
    fireEvent.click(screen.getByRole('button', { name: 'MIS corrections' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Nairobi/);
    fireEvent.click(screen.getByRole('button', { name: 'Accept MIS value' }));
    await waitFor(() =>
      expect(postApi).toHaveBeenCalledWith(
        '/participants/corrections/c1/resolve',
        {
          action: 'accept',
          note: '',
        },
      ),
    );
  });

  it('asks the server for the chosen state', async () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'MIS corrections' }));
    await screen.findByText(/corrected to/);
    fireEvent.click(screen.getByRole('button', { name: 'Done in MIS' }));
    await waitFor(() =>
      expect(
        getApi.mock.calls.some((c) => String(c[0]).includes('state=confirmed')),
      ).toBe(true),
    );
  });
});
