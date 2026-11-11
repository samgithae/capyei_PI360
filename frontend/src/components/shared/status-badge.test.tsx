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

describe('StatusBadge labels', () => {
  it('turns a code with underscores into words', () => {
    render(<StatusBadge status="under_review" />);
    expect(screen.getByText('under review')).toBeInTheDocument();
  });

  it('prefers the label the API sends', () => {
    render(<StatusBadge status="interview" label="Interview or assessment" />);
    expect(screen.getByText('Interview or assessment')).toBeInTheDocument();
  });
});
