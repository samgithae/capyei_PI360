import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ReportPage } from './report-page';
import type { Report } from './report-types';
import { ReportsIndexPage } from './reports-index-page';

const api = vi.fn();
const postFile = vi.fn();
const saveBlob = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  postFile: (...a: unknown[]) => postFile(...a),
  ApiError: class extends Error {
    status = 0;
  },
}));
vi.mock('@/pages/participants/cv/download-cv-button', () => ({
  saveBlob: (...a: unknown[]) => saveBlob(...a),
}));
vi.mock('recharts', async (orig) => {
  const real = await orig<typeof import('recharts')>();
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
  };
});

const SUMMARIES = [
  {
    slug: 'programme-scorecard',
    title: 'Programme scorecard',
    purpose: 'How many youth were trained, referred and placed.',
    audience: 'Directors, donors',
    filters: ['period', 'county'],
    period_on: 'when the cohort started',
  },
  {
    slug: 'retention',
    title: 'Retention after placement',
    purpose: 'Whether placed youth are still employed.',
    audience: 'Donors, management',
    filters: ['period'],
    period_on: 'the placement start date',
  },
];
const OPTIONS = {
  programmes: [],
  cohorts: [],
  institutions: [],
  counties: [
    { id: 'c1', name: 'Kisumu' },
    { id: 'c2', name: 'Nairobi' },
  ],
  sectors: [],
  employers: [],
  pathways: [],
  genders: [],
  stages: [],
  checkins: [],
};
const REPORT: Report = {
  slug: 'programme-scorecard',
  title: 'Programme scorecard',
  purpose: '',
  audience: '',
  period_on: 'when the cohort started',
  generated_on: '2026-11-19',
  filters_applied: [],
  tiles: [
    { id: 'reg', label: 'Registered youth', value: 44, unit: '', hint: '' },
    { id: 'rate', label: 'Placement rate', value: null, unit: '%', hint: '' },
  ],
  charts: [
    {
      id: 'funnel',
      title: 'From registration to placement',
      type: 'bar',
      categories: ['Registered', 'Placed'],
      series: [{ name: 'Youth', values: [44, 0] }],
      unit: '',
      empty: '',
    },
    {
      id: 'empty',
      title: 'Placed by year',
      type: 'column',
      categories: [],
      series: [],
      unit: '',
      empty: 'No enrolments match these filters.',
    },
  ],
  tables: [
    {
      id: 'cohorts',
      title: 'By cohort',
      columns: ['Cohort', 'Enrolled'],
      rows: [['Go Blue 2021', 20]],
    },
  ],
  definitions: [
    { name: 'Placed', meaning: 'Has a placement.', approved: true },
    { name: 'Period', meaning: 'Cohort start.', approved: false },
  ],
  notes: ['Disability is not collected yet.'],
};

function open(path: string) {
  api.mockImplementation((url: string) => {
    if (url === '/reporting/reports')
      return Promise.resolve({ reports: SUMMARIES });
    if (url === '/reporting/reports/filters') return Promise.resolve(OPTIONS);
    return Promise.resolve(REPORT);
  });
  render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/reports" element={<ReportsIndexPage />} />
            <Route path="/reports/:slug" element={<ReportPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe('Reports', () => {
  beforeEach(() => {
    api.mockReset();
    postFile.mockReset();
    saveBlob.mockReset();
  });

  it('lists the reports as links to their own pages', async () => {
    open('/reports');
    const link = await screen.findByRole('link', {
      name: /Retention after placement/,
    });
    expect(link.getAttribute('href')).toBe('/reports/retention');
  });

  it('shows tiles, tables, notes and definitions, with n/a for a missing rate', async () => {
    open('/reports/programme-scorecard');
    expect(await screen.findByText('Registered youth')).toBeTruthy();
    expect(screen.getAllByText('44').length).toBeGreaterThan(0);
    expect(screen.getAllByText('n/a').length).toBeGreaterThan(0);
    expect(screen.getByText('Go Blue 2021')).toBeTruthy();
    expect(screen.getByText('Disability is not collected yet.')).toBeTruthy();
    expect(screen.getByText('Working definition')).toBeTruthy();
    expect(screen.getByText('No enrolments match these filters.')).toBeTruthy();
  });

  it('sends the chosen filters to the server and can clear them', async () => {
    open('/reports/programme-scorecard?county=c1');
    await screen.findByText('Registered youth');
    expect(
      api.mock.calls.some(
        (c) => c[0] === '/reporting/reports/programme-scorecard?county=c1',
      ),
    ).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /Clear filters/ }));
    await waitFor(() =>
      expect(
        api.mock.calls.some(
          (c) => c[0] === '/reporting/reports/programme-scorecard?',
        ),
      ).toBe(true),
    );
  });

  it('exports with the same filters as the page', async () => {
    postFile.mockResolvedValue({ blob: new Blob(['x']), filename: 'r.xlsx' });
    open('/reports/programme-scorecard?county=c1');
    await screen.findByText('Registered youth');
    fireEvent.pointerDown(screen.getByRole('button', { name: /Export/ }), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByText('Excel workbook'));
    await waitFor(() => expect(saveBlob).toHaveBeenCalled());
    expect(postFile.mock.calls[0][0]).toBe(
      '/reporting/reports/programme-scorecard/export?file_format=xlsx&county=c1',
    );
  });
});
