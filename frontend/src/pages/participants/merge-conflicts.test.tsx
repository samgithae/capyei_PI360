import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  CriticalList,
  PlacementResolver,
  ResolutionList,
  unchosen,
  type Critical,
  type ReviewField,
} from './merge-conflicts';

// Synthetic data only.
const fields: ReviewField[] = [
  {
    field: 'gender',
    label: 'Gender',
    survivor: 'female',
    merged: 'male',
    conflict: true,
    keep: null,
  },
  {
    field: 'age_at_source',
    label: 'Age',
    survivor: null,
    merged: 22,
    conflict: false,
    keep: 'merged',
  },
];

const two: Critical = {
  code: 'two_running_placements',
  message: 'Both records have a running placement.',
  hint: 'Keep one or end one.',
  actions: ['end', 'same'],
  looks_same: true,
  items: [
    {
      id: 'p1',
      side: 'survivor',
      employer: 'Test Bakery',
      start_date: '2026-01-05',
    },
    {
      id: 'p2',
      side: 'merged',
      employer: 'Test Bakery',
      start_date: '2026-01-05',
    },
  ],
};

function resolver(canEdit = true) {
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <PlacementResolver
        candidateId="c1"
        conflict={two}
        canEditPlacements={canEdit}
        onDone={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe('merge conflicts', () => {
  it('lists only real conflicts that are not chosen yet', () => {
    expect(unchosen(fields, {})).toEqual(['Gender']);
    expect(unchosen(fields, { gender: 'survivor' })).toEqual([]);
  });

  it('says the merge will wait and names both placements', () => {
    render(<CriticalList conflicts={[two]} />);
    expect(screen.getByText(/will wait for 1 conflict/)).toBeInTheDocument();
    expect(screen.getByText(/kept record: Test Bakery/)).toBeInTheDocument();
    expect(screen.getByText(/merged record: Test Bakery/)).toBeInTheDocument();
  });

  it('shows nothing when no conflict holds the merge', () => {
    const { container } = render(<CriticalList conflicts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('needs a placement, a choice and a reason before recording', () => {
    resolver();
    const record = screen.getByRole('button', { name: 'Record resolution' });
    expect(record).toBeDisabled();
    expect(
      screen.getByText(/look like the same placement/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/merged record: Test Bakery/));
    fireEvent.click(screen.getByLabelText(/recorded twice/));
    expect(record).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Resolution reason'), {
      target: { value: 'One job captured twice' },
    });
    expect(record).toBeEnabled();
  });

  it('asks for an end date when the placements differ', () => {
    resolver();
    fireEvent.click(screen.getByLabelText(/merged record: Test Bakery/));
    fireEvent.click(screen.getByLabelText(/this one has ended/));
    fireEvent.change(screen.getByLabelText('Resolution reason'), {
      target: { value: 'Left' },
    });
    expect(
      screen.getByRole('button', { name: 'Record resolution' }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText('End date'), {
      target: { value: '2025-12-31' },
    });
    expect(
      screen.getByRole('button', { name: 'Record resolution' }),
    ).toBeEnabled();
  });

  it('tells officers without placement rights why they cannot resolve', () => {
    resolver(false);
    expect(
      screen.getByText(/needs the right to edit placements/),
    ).toBeInTheDocument();
  });

  it('records who resolved what and why', () => {
    render(
      <ResolutionList
        rows={[
          {
            id: 'r1',
            conflict: 'two_running_placements',
            action: 'same',
            reason: 'One job',
            decided_by: 'steward',
            decided_at: '2026-11-23T10:00:00Z',
          },
        ]}
      />,
    );
    expect(
      screen.getByText(
        /steward marked a placement as recorded twice on 2026-11-23/,
      ),
    ).toBeInTheDocument();
  });
});
