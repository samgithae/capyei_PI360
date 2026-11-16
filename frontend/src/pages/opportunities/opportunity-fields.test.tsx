import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  switchEmployer,
  WhereWhatFields,
  type WhereWhat,
} from './opportunity-fields';

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  ApiError: class extends Error {},
}));
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

const EMPLOYERS: Record<string, unknown> = {
  coast: {
    counties: [
      { id: 'nbi', name: 'Nairobi' },
      { id: 'msa', name: 'Mombasa' },
    ],
    sectors: [
      { id: 'hos', name: 'Hospitality' },
      { id: 'ict', name: 'ICT' },
    ],
  },
  lake: {
    counties: [{ id: 'ksm', name: 'Kisumu' }],
    sectors: [{ id: 'ret', name: 'Retail' }],
  },
  bare: { counties: [], sectors: [] },
};

const BLANK: WhereWhat = {
  sector_ids: [],
  county_ids: [],
  location: '',
  description: '',
  start_date: null,
  closing_date: null,
};

function show(
  employerId: string,
  value: WhereWhat = BLANK,
  onChange = vi.fn(),
  stored?: React.ComponentProps<typeof WhereWhatFields>['stored'],
) {
  const ui = (id: string) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WhereWhatFields
          idPrefix="t"
          employerId={id}
          value={value}
          onChange={onChange}
          stored={stored}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const client = new QueryClient();
  const r = render(ui(employerId));
  return { onChange, again: (id: string) => r.rerender(ui(id)) };
}
const optionsOf = (label: string) =>
  within(screen.getByRole('combobox', { name: label }))
    .getAllByRole('option')
    .map((o) => o.textContent)
    .filter(Boolean);

describe('opportunity counties and industries follow the employer', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockImplementation((path: string) =>
      Promise.resolve(EMPLOYERS[path.split('/').pop() ?? '']),
    );
  });

  it('offers only that employer’s counties and sectors, and saves the picks', async () => {
    const { onChange } = show('coast');
    await screen.findByRole('combobox', { name: 'Add a county' });
    expect(optionsOf('Add a county')).toEqual(['Nairobi', 'Mombasa']);
    expect(optionsOf('Add an industry / sector')).toEqual([
      'Hospitality',
      'ICT',
    ]);
    fireEvent.change(screen.getByRole('combobox', { name: 'Add a county' }), {
      target: { value: 'nbi' },
    });
    expect(onChange).toHaveBeenCalledWith({ county_ids: ['nbi'] });
    fireEvent.change(
      screen.getByRole('combobox', { name: 'Add an industry / sector' }),
      { target: { value: 'hos' } },
    );
    expect(onChange).toHaveBeenCalledWith({ sector_ids: ['hos'] });
  });

  it('reloads both lists when the employer changes', async () => {
    const { again } = show('coast');
    await screen.findByRole('combobox', { name: 'Add a county' });
    again('lake');
    await screen.findByRole('option', { name: 'Kisumu' });
    expect(optionsOf('Add a county')).toEqual(['Kisumu']);
    expect(optionsOf('Add an industry / sector')).toEqual(['Retail']);
  });

  it('asks for an employer first when none is chosen', () => {
    show('');
    expect(screen.getAllByText(/Choose an employer first/)).toHaveLength(2);
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('tells the user, with a link, when the employer has no counties or sectors', async () => {
    show('bare');
    const link = await screen.findAllByRole('link', {
      name: 'Add them on the employer profile',
    });
    expect(link).toHaveLength(2);
    expect(link[0].getAttribute('href')).toBe('/employers/bare');
    expect(screen.getAllByText(/This employer has no/)).toHaveLength(2);
  });

  it('flags a stored value the employer no longer lists, by name', async () => {
    show('coast', { ...BLANK, county_ids: ['ksm'] }, vi.fn(), {
      counties: [{ id: 'ksm', name: 'Kisumu' }],
      sectors: [],
    });
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Kisumu is not among this employer’s counties',
    );
    expect(screen.getByRole('button', { name: 'Remove Kisumu' })).toBeTruthy();
  });
});

describe('switchEmployer', () => {
  const v = {
    employer_id: 'coast',
    county_ids: ['nbi'],
    sector_ids: ['hos'],
    title: 'Front desk',
  };

  it('clears the counties and sectors when another employer is chosen', () => {
    const { next, cleared } = switchEmployer(v, 'lake');
    expect(next).toMatchObject({
      employer_id: 'lake',
      county_ids: [],
      sector_ids: [],
      title: 'Front desk',
    });
    expect(cleared).toBe(true);
  });

  it('keeps everything when the same employer is chosen again', () => {
    const { next, cleared } = switchEmployer(v, 'coast');
    expect(next).toBe(v);
    expect(cleared).toBe(false);
  });

  it('does not report a clear when nothing was picked', () => {
    const { cleared } = switchEmployer(
      { ...v, county_ids: [], sector_ids: [] },
      'lake',
    );
    expect(cleared).toBe(false);
  });
});
