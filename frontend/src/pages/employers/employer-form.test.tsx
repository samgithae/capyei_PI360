import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EmployerForm, EMPTY, type EmployerValues } from './employer-form';

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: () => true }),
}));
// Native <select> stands in for the searchable popover (tested on its own).
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

const OPTIONS = {
  counties: [
    { id: 'nbi', name: 'Nairobi' },
    { id: 'msa', name: 'Mombasa' },
    { id: 'ksm', name: 'Kisumu' },
  ],
  sectors: [
    { id: 'hos', name: 'Hospitality' },
    { id: 'ict', name: 'ICT' },
    { id: 'ret', name: 'Retail' },
  ],
};

function show(
  initial: EmployerValues,
  onSave = vi.fn().mockResolvedValue(undefined),
) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <EmployerForm initial={initial} options={OPTIONS} onSave={onSave} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onSave;
}
const pick = (label: string, id: string) =>
  fireEvent.change(screen.getByRole('combobox', { name: label }), {
    target: { value: id },
  });

describe('EmployerForm counties and sectors', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockResolvedValue({ matches: [] });
  });

  it('saves several counties and several industries / sectors', async () => {
    const onSave = show(EMPTY);
    fireEvent.change(screen.getByLabelText('Employer name'), {
      target: { value: 'Coast Hotels' },
    });
    pick('Add a county', 'nbi');
    pick('Add a county', 'msa');
    pick('Add an industry / sector', 'hos');
    pick('Add an industry / sector', 'ict');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const [values] = onSave.mock.calls[0];
    expect(values.county_ids).toEqual(['nbi', 'msa']);
    expect(values.sector_ids).toEqual(['hos', 'ict']);
  });

  it('labels the sector field "Industry / Sector"', () => {
    show(EMPTY);
    expect(screen.getByText('Industry / Sector')).toBeTruthy();
    expect(screen.getByText('Counties')).toBeTruthy();
  });

  it('reopens with all four chosen values and lets them be edited', async () => {
    const onSave = show({
      ...EMPTY,
      name: 'Coast Hotels',
      county_ids: ['nbi', 'msa'],
      sector_ids: ['hos', 'ict'],
    });
    for (const n of ['Nairobi', 'Mombasa', 'Hospitality', 'ICT']) {
      expect(screen.getByRole('button', { name: `Remove ${n}` })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole('button', { name: 'Remove Mombasa' }));
    pick('Add a county', 'ksm');
    fireEvent.click(screen.getByRole('button', { name: 'Remove ICT' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const [values] = onSave.mock.calls[0];
    expect(values.county_ids).toEqual(['nbi', 'ksm']);
    expect(values.sector_ids).toEqual(['hos']);
  });

  it('asks for a sub-county only when the employer has exactly one county', async () => {
    api.mockImplementation((path: string) =>
      Promise.resolve(path.includes('sub-counties') ? [] : { matches: [] }),
    );
    show({ ...EMPTY, county_ids: ['nbi'] });
    expect(screen.getByLabelText('Sub-county')).toBeTruthy();
    pick('Add a county', 'msa');
    await waitFor(() =>
      expect(screen.queryByLabelText('Sub-county')).toBeNull(),
    );
    expect(
      screen.getByText(/only recorded when the employer has one county/),
    ).toBeTruthy();
  });
});
