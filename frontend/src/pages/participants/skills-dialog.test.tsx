import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CapabilityFields,
  draftToPayload,
  emptyDraft,
  type CapabilityDraft,
  type CapabilityOptions,
} from './capability-fields';
import { SkillsCard } from './cv/cv-editor';
import type { CvProfileData } from './cv/cv-types';

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: vi.fn(),
  ApiError: class extends Error {},
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), info: vi.fn() } }));

const ROWS = [
  { id: 's1', name: 'Welding', category: 'Trades' },
  { id: 's2', name: 'Plumbing', category: 'Trades' },
];
function server(path: string) {
  const url = new URL(path, 'http://x');
  if (url.pathname.endsWith('/categories'))
    return { results: [{ name: 'Trades', count: 2 }] };
  if (url.pathname.endsWith('/popular'))
    return { results: [{ ...ROWS[0], used: 1 }] };
  return { total: 2, results: ROWS };
}
beforeEach(() => {
  api.mockReset();
  api.mockImplementation((p: string) => Promise.resolve(server(p)));
});
const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {ui}
    </QueryClientProvider>,
  );

const profile = (skills: CvProfileData['skills']) =>
  ({ skills, options: { skills: [] } }) as unknown as CvProfileData;

describe('Choose skills on the youth CV editor', () => {
  it('replaces the dropdown with a dialog on the audience’s own routes, and saves ids + levels', async () => {
    const mutate = vi.fn();
    wrap(
      <SkillsCard
        endpoint="/youth/skills"
        profile={profile([
          {
            id: 'row1',
            skill_id: 's1',
            skill: 'Welding',
            proficiency: 3,
            source: 'youth',
            verified: false,
            verified_by: '',
          },
        ])}
        save={{ mutate, isError: false, isPending: false } as never}
      />,
    );
    expect(screen.queryByText('Add a skill')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Choose skills/ }));
    expect(
      await screen.findByPlaceholderText('Search or add a skill...'),
    ).toBeInTheDocument();
    // the saved skill is already selected
    expect(screen.getByLabelText('Selected skills')).toHaveTextContent(
      'Selected Skills (1)',
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Plumbing' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save skills' }));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      skills: [
        // a skill already held keeps its row id; the server matches rows by id
        { id: 'row1', skill_id: 's1', proficiency: 3 },
        { id: undefined, skill_id: 's2', proficiency: 2 },
      ],
    });
    expect(
      api.mock.calls.every(([p]) => String(p).startsWith('/youth/skills')),
    ).toBe(true);
  });
});

describe('Choose skills when adding a youth', () => {
  const options = {
    levels: [],
    grades: [],
    skills: [{ id: 's1', name: 'Welding' }],
    sectors: [],
    work_patterns: [],
  } as CapabilityOptions;
  let latest: CapabilityDraft = emptyDraft();
  function Harness() {
    const [d, setD] = useState<CapabilityDraft>(emptyDraft());
    latest = d;
    return <CapabilityFields value={d} onChange={setD} options={options} />;
  }

  it('picks several skills in one go and keeps them as chips with a level', async () => {
    wrap(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: /Choose skills/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Plumbing' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Welding' })[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(latest.skills).toHaveLength(2));
    // chips show the name even for a skill that is not in the preloaded options
    expect(screen.getByLabelText('Level of Plumbing')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Level of Plumbing'), {
      target: { value: '3' },
    });
    expect(draftToPayload(latest, true).skills).toEqual([
      { id: undefined, skill_id: 's2', proficiency: 3 },
      { id: undefined, skill_id: 's1', proficiency: 2 },
    ]);
    fireEvent.click(screen.getByLabelText('Remove Plumbing'));
    expect(latest.skills.map((s) => s.skill_id)).toEqual(['s1']);
  });
});
