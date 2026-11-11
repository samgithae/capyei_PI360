import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusBadge } from './status-badge';

describe('StatusBadge', () => {
  it('always shows the status as text, not colour alone', () => {
    render(<StatusBadge status="open" />);
    expect(screen.getByText('open')).toBeInTheDocument();
  });

  it('renders an unknown backend status instead of breaking', () => {
    render(<StatusBadge status="brand-new-status" />);
    expect(screen.getByText('brand-new-status')).toBeInTheDocument();
  });
});
