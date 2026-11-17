import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CvCompletion } from './cv-completion';
import { CvDocument } from './cv-document';
import { CvProfile } from './cv-profile';
import type { CvDoc } from './cv-types';

const api = vi.fn();
const apiFile = vi.fn();
const clicked: string[] = [];
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  apiFile: (...a: unknown[]) => apiFile(...a),
  apiUrl: (p: string) => `/api/v1${p}`,
  del: vi.fn(),
  upload: vi.fn(),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: () => true }),
}));

const base: CvDoc = {
  name: 'Samuel Kamau',
  name_parts: { first: 'Samuel', middle: '', last: 'Kamau' },
  headline: 'Welder',
  has_photo: false,
  contact: {
    phone: '0712345678',
    email: 'sam@example.com',
    location: 'Nairobi',
    county: 'Nairobi',
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
};

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );

describe('CvDocument', () => {
  it('shows only the sections that have content', () => {
    render(<CvDocument cv={base} />);
    expect(screen.getByText('Samuel Kamau')).toBeTruthy();
    expect(screen.getByText('Professional summary')).toBeTruthy();
    expect(screen.queryByText('Work experience')).toBeNull();
    expect(screen.queryByText('Education')).toBeNull();
    expect(screen.queryByText('Skills')).toBeNull();
  });

  it('says so when the youth has no formal work experience', () => {
    render(<CvDocument cv={{ ...base, no_work_experience: true }} />);
    expect(screen.getByText('Work experience')).toBeTruthy();
    expect(screen.getByText('No formal work experience yet.')).toBeTruthy();
  });

  it('lists experience and skills', () => {
    render(
      <CvDocument
        cv={{
          ...base,
          experience: [
            {
              title: 'Welder',
              employer: 'Jua Kali Ltd',
              employment_type: 'Full time',
              period: 'Jan 2022 - Present',
              duration: '2 yrs',
              responsibilities: 'Cut metal\nWeld frames',
              achievements: '',
            },
          ],
          skills: [{ name: 'MIG welding', level: 'Advanced' }],
        }}
      />,
    );
    expect(screen.getByText('Cut metal')).toBeTruthy();
    expect(screen.getByText('MIG welding')).toBeTruthy();
    expect(screen.getByText('Jan 2022 - Present | 2 yrs')).toBeTruthy();
  });
});

describe('CvProfile', () => {
  beforeEach(() => {
    api.mockReset();
    apiFile.mockReset();
    clicked.length = 0;
    URL.createObjectURL = vi.fn(() => 'blob:cv');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this.download);
    });
  });

  it('shows the completion figure with what is missing', async () => {
    api.mockResolvedValue({
      ...base,
      completeness: {
        percent: 50,
        missing: [
          { key: 'education', label: 'Education', hint: 'Add one record.' },
        ],
        suggestions: [],
      },
    });
    wrap(<CvProfile id="abc" />);
    expect(await screen.findByText('This CV is 50% complete')).toBeTruthy();
    expect(screen.getByText('Add one record.')).toBeTruthy();
    expect(api).toHaveBeenCalledWith('/participants/abc/cv');
  });

  it("leaves a youth's own completion card to the profile page", async () => {
    api.mockResolvedValue(base);
    wrap(<CvProfile id="me" self />);
    await screen.findByText('My CV');
    expect(screen.queryByText(/complete/i)).toBeNull();
  });

  it('downloads the saved CV under the name the server gives', async () => {
    api.mockResolvedValue(base);
    apiFile.mockResolvedValue({
      blob: new Blob(['%PDF']),
      filename: 'Samuel_Kamau_CV.pdf',
    });
    wrap(<CvProfile id="me" self />);
    await screen.findByText('My CV');
    fireEvent.click(screen.getAllByText('Download CV (PDF)')[0]);
    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(apiFile).toHaveBeenCalledWith('/youth/cv.pdf');
    expect(clicked[0]).toBe('Samuel_Kamau_CV.pdf');
  });

  it('staff read the CV of the youth by id', async () => {
    api.mockResolvedValue(base);
    wrap(<CvProfile id="abc" />);
    await screen.findByText('Samuel Kamau');
    expect(api).toHaveBeenCalledWith('/participants/abc/cv');
  });
});

describe('CvCompletion', () => {
  const doc = (percent: number) =>
    ({
      ...base,
      completeness: {
        percent,
        missing:
          percent < 100
            ? [{ key: 'skills', label: 'Skills', hint: 'Add three skills.' }]
            : [],
        suggestions: [],
      },
    }) as CvDoc;

  it('tells the youth how complete the CV is and what to add', () => {
    wrap(<CvCompletion cv={doc(70)} onEdit={() => undefined} />);
    expect(screen.getByText('Your CV is 70% complete')).toBeTruthy();
    expect(screen.getByText('Add three skills.')).toBeTruthy();
    expect(screen.getByText('Complete my CV')).toBeTruthy();
  });

  it('opens the editor from the button', () => {
    const onEdit = vi.fn();
    wrap(<CvCompletion cv={doc(40)} onEdit={onEdit} />);
    fireEvent.click(screen.getByText('Complete my CV'));
    expect(onEdit).toHaveBeenCalled();
  });

  it('the compact dashboard card links to the editor and hides at 100%', () => {
    wrap(<CvCompletion cv={doc(70)} linkToProfile compact />);
    expect(screen.getByText(/Still to add: skills/)).toBeTruthy();
    expect(
      screen.getByText('Complete my CV').closest('a')?.getAttribute('href'),
    ).toBe('/me/profile?cv=edit#my-cv');
  });

  it('is only a congratulation at 100%, with no button', () => {
    wrap(<CvCompletion cv={doc(100)} />);
    expect(screen.getByText(/Your CV is complete/)).toBeTruthy();
    expect(screen.queryByText('Complete my CV')).toBeNull();
  });
});
