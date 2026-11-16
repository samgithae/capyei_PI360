import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MultiSelectField } from './multi-select-field';

// The searchable popover is its own tested component; a native <select> keeps these tests about
// what this component adds: chips, removal, no duplicates, and the loading and empty states.
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

const COUNTIES = [
  { id: 'c1', name: 'Nairobi' },
  { id: 'c2', name: 'Mombasa' },
  { id: 'c3', name: 'Kisumu' },
];

function Harness({
  initial = [],
  ...rest
}: { initial?: string[] } & Partial<
  React.ComponentProps<typeof MultiSelectField>
>) {
  const [value, setValue] = useState(initial);
  return (
    <MultiSelectField
      label="Add a county"
      options={COUNTIES}
      value={value}
      onChange={setValue}
      {...rest}
    />
  );
}

describe('MultiSelectField', () => {
  it('adds several choices as chips and never offers a chosen one again', () => {
    render(<Harness />);
    const picker = screen.getByRole('combobox', { name: 'Add a county' });
    fireEvent.change(picker, { target: { value: 'c1' } });
    fireEvent.change(picker, { target: { value: 'c2' } });
    const chips = screen.getByRole('list', { name: 'Chosen: Add a county' });
    expect(within(chips).getByText('Nairobi')).toBeTruthy();
    expect(within(chips).getByText('Mombasa')).toBeTruthy();
    const offered = within(picker)
      .getAllByRole('option')
      .map((o) => o.textContent);
    expect(offered).toEqual(['', 'Kisumu']);
  });

  it('removes a chip and offers the choice again', () => {
    render(<Harness initial={['c1', 'c2']} />);
    fireEvent.click(screen.getByRole('button', { name: 'Remove Nairobi' }));
    expect(screen.queryByRole('button', { name: 'Remove Nairobi' })).toBeNull();
    expect(screen.getByRole('option', { name: 'Nairobi' })).toBeTruthy();
  });

  it('shows the name of an old value that is not among the options', () => {
    render(
      <Harness
        initial={['gone']}
        labels={[{ id: 'gone', name: 'Old county' }]}
      />,
    );
    expect(screen.getByText('Old county')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Remove Old county' }),
    ).toBeTruthy();
  });

  it('is disabled while the options load', () => {
    render(<Harness options={[]} loading />);
    expect(screen.getByRole('combobox', { name: 'Loading…' })).toBeDisabled();
  });

  it('explains an empty list instead of showing a dead picker', () => {
    render(
      <Harness options={[]} emptyMessage="This employer has no counties." />,
    );
    expect(screen.getByRole('status').textContent).toContain(
      'This employer has no counties.',
    );
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('disables the picker once everything is chosen', () => {
    render(<Harness initial={['c1', 'c2', 'c3']} />);
    expect(screen.getByRole('combobox')).toBeDisabled();
  });
});
