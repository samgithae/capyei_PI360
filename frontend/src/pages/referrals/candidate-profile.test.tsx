import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CandidateProfile, WhySuggested, type Fit } from './candidate-profile';

const api = vi.fn();
const apiFile = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  apiFile: (...a: unknown[]) => apiFile(...a),
  apiUrl: (p: string) => `/api/v1${p}`,
  ApiError: class extends Error {},
}));

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );

const fit: Fit = {
  origin: 'officer',
  available: true,
  group: 'eligible_with_unknowns',
  met: 1,
  checked: 3,
  checks: [
    {
      label: 'Diploma',
      mandatory: true,
      outcome: 'pass',
      note: 'Holds a diploma.',
      source: null,
      verified: null,
    },
    {
      label: 'Cooking',
      mandatory: true,
      outcome: 'unknown',
      note: 'No skills recorded.',
      source: null,
      verified: null,
    },
  ],
  not_checked: [{ label: 'Free text only' }],
};

describe('WhySuggested', () => {
  beforeEach(() => api.mockReset());

  it('lists each requirement with what was found', async () => {
    api.mockResolvedValue(fit);
    wrap(<WhySuggested id="r1" origin="officer" />);
    expect(await screen.findByText('Diploma')).toBeTruthy();
    expect(screen.getByText('Holds a diploma.')).toBeTruthy();
    expect(screen.getByLabelText('Not recorded')).toBeTruthy();
    // the engine's technical note is replaced by plain wording
    expect(screen.queryByText('No skills recorded.')).toBeNull();
    expect(screen.getByText(/Nothing recorded on the youth/)).toBeTruthy();
    expect(screen.getByText(/1 of 3 checks met/)).toBeTruthy();
    expect(screen.getByText(/Free text only/)).toBeTruthy();
    expect(api).toHaveBeenCalledWith('/referrals/r1/fit');
  });

  it('says so when the youth applied themselves', async () => {
    api.mockResolvedValue(fit);
    wrap(<WhySuggested id="r1" origin="trainee" />);
    expect(
      await screen.findByText(/applied for this opportunity/),
    ).toBeTruthy();
  });

  it('explains why there is no analysis instead of leaving a blank', async () => {
    api.mockResolvedValue({
      origin: 'officer',
      available: false,
      reason: 'No compatibility rule is active yet.',
    });
    wrap(<WhySuggested id="r1" origin="officer" />);
    expect(await screen.findByText('No fit analysis yet')).toBeTruthy();
    expect(screen.getByText(/No compatibility rule/)).toBeTruthy();
  });
});

describe('CandidateProfile', () => {
  beforeEach(() => {
    api.mockReset();
    apiFile.mockReset();
    URL.createObjectURL = vi.fn(() => 'blob:cv');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  it('links to the full profile and downloads the CV the employer would get', async () => {
    api.mockResolvedValue({
      name: 'Samuel Kamau',
      headline: 'Welder',
      has_photo: false,
      contact: {
        phone: '',
        email: '',
        location: '',
        county: '',
        sub_county: '',
      },
      summary: 'A hard working welder.',
      education: [],
      experience: [],
      no_work_experience: false,
      practical: [],
      skills: [],
      certifications: [],
      languages: [],
      preferences: null,
      completeness: { percent: 50, missing: [], suggestions: [] },
    });
    apiFile.mockResolvedValue({ blob: new Blob(['x']), filename: 'cv.pdf' });
    wrap(<CandidateProfile participantId="p1" />);
    expect(await screen.findByText('Samuel Kamau')).toBeTruthy();
    expect(
      screen
        .getByRole('link', { name: /View full profile/ })
        .getAttribute('href'),
    ).toBe('/youth/p1');
    fireEvent.click(screen.getByRole('button', { name: /Download CV/ }));
    await waitFor(() =>
      expect(apiFile).toHaveBeenCalledWith('/participants/p1/cv.pdf'),
    );
  });
});
