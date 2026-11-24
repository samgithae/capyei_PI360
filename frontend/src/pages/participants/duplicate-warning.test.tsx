import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { DuplicateWarning, type SimilarMatch } from './duplicate-warning';

const match: SimilarMatch = {
  id: 'p1',
  name: 'John Kamau Mwangi',
  status: 'active',
  county: 'Kisumu',
  projects: ['Go Blue'],
  reasons: [
    { code: 'similar_name', text: 'Almost the same name' },
    { code: 'same_phone', text: 'Same phone number and a similar name' },
  ],
};

function show(matches: SimilarMatch[], onContinue = vi.fn()) {
  render(
    <MemoryRouter>
      <DuplicateWarning matches={matches} onContinue={onContinue} />
    </MemoryRouter>,
  );
  return onContinue;
}

describe('DuplicateWarning', () => {
  it('renders nothing when there are no matches', () => {
    show([]);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('names the person, tells them apart and says why they matched', () => {
    show([match]);
    expect(screen.getByRole('link', { name: match.name })).toHaveAttribute(
      'href',
      '/youth/p1',
    );
    expect(screen.getByText(/active, Kisumu, Go Blue/)).toBeInTheDocument();
    expect(
      screen.getByText(
        'Almost the same name; Same phone number and a similar name',
      ),
    ).toBeInTheDocument();
  });

  it('lets the user carry on', () => {
    const onContinue = show([match]);
    fireEvent.click(screen.getByRole('button', { name: 'continue anyway' }));
    expect(onContinue).toHaveBeenCalledOnce();
  });
});
