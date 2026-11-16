import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EditOpportunity } from './opportunity-edit';

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  ApiError: class extends Error {},
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), info: vi.fn() } }));
vi.mock('@/components/shared/select-field', () => ({
  SelectField: ({
    label,
    options,
    onChange,
    disabled,
  }: {
    label: string;
    options: { id: string; name: string }[];
    onChange: (v: string) => void;
    disabled?: boolean;
  }) => (
    <select
      aria-label={label}
      disabled={disabled}
      value=""
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" />
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </select>
  ),
}));

const OPPORTUNITY = {
  title: 'Front desk',
  kind: 'job',
  employer_id: 'coast',
  counties: [{ id: 'nbi', name: 'Nairobi' }],
  county_ids: ['nbi'],
  sectors: [{ id: 'hos', name: 'Hospitality' }],
  sector_ids: ['hos'],
  location: '',
  positions: 1,
  description: '',
  closing_date: null,
  start_date: null,
};
const EMPLOYER = {
  counties: [
    { id: 'nbi', name: 'Nairobi' },
    { id: 'msa', name: 'Mombasa' },
  ],
  sectors: [
    { id: 'hos', name: 'Hospitality' },
    { id: 'ict', name: 'ICT' },
  ],
};

describe('EditOpportunity', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockImplementation((path: string, init?: { method?: string }) => {
      if (init?.method === 'PATCH') return Promise.resolve({});
      return Promise.resolve(
        path.startsWith('/opportunities/') ? OPPORTUNITY : EMPLOYER,
      );
    });
  });

  it('loads the stored counties and sectors and saves the edited ones', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <EditOpportunity id="o1" onClose={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole('button', { name: 'Remove Nairobi' }),
    ).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Remove Hospitality' }),
    ).toBeTruthy();
    // only the employer's other county is offered
    await screen.findByRole('option', { name: 'Mombasa' });
    fireEvent.change(screen.getByRole('combobox', { name: 'Add a county' }), {
      target: { value: 'msa' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        '/opportunities/o1',
        expect.objectContaining({ method: 'PATCH' }),
      ),
    );
    const call = api.mock.calls.find((c) => c[1]?.method === 'PATCH')!;
    const body = JSON.parse(call[1].body);
    expect(body.county_ids).toEqual(['nbi', 'msa']);
    expect(body.sector_ids).toEqual(['hos']);
  });
});
