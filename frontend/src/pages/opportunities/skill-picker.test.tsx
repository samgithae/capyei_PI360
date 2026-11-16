import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SkillPickerDialog, type PickedSkill } from './skill-picker';

const api = vi.fn();
const post = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: (...a: unknown[]) => post(...a),
  ApiError: class extends Error {
    constructor(
      public status: number,
      message: string,
      public errors: { code: string }[] = [],
      public code = '',
      public body: Record<string, unknown> = {},
    ) {
      super(message);
    }
  },
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), info: vi.fn() } }));
vi.mock('@/components/shared/select-field', () => ({
  SelectField: ({
    label,
    options,
    value,
    onChange,
  }: {
    label: string;
    options: { id: string; name: string }[];
    value: string;
    onChange: (v: string) => void;
  }) => (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </select>
  ),
}));

const row = (id: string, name: string, category = 'Trades') => ({
  id,
  name,
  category,
});
const TRADES = [
  'Welding',
  'Plumbing',
  'Carpentry',
  'Tailoring',
  'Masonry',
  'Painting',
  'Hairdressing',
  'Motor repair',
].map((n, i) => row(`t${i}`, n));
const ALL = [...TRADES, row('o1', 'Bookkeeping', 'Office')];

/** A small fake of the skills endpoints: partial search, category filter, offset paging. */
function server(path: string) {
  const url = new URL(path, 'http://x');
  if (url.pathname === '/requirement-skills/categories')
    return {
      results: [
        { name: 'Trades', count: TRADES.length },
        { name: 'Office', count: 1 },
      ],
    };
  if (url.pathname === '/requirement-skills/popular')
    return { results: [{ ...TRADES[0], used: 3 }] };
  if (url.pathname === '/requirement-skills') {
    const q = (url.searchParams.get('q') ?? '').toLowerCase();
    const cat = url.searchParams.get('category');
    const limit = Number(url.searchParams.get('limit'));
    const offset = Number(url.searchParams.get('offset'));
    const hits = ALL.filter(
      (s) =>
        (!cat || s.category === cat) &&
        (!q || s.name.toLowerCase().includes(q)),
    );
    return { total: hits.length, results: hits.slice(offset, offset + limit) };
  }
  throw new Error(`unexpected ${path}`);
}

function setup(
  props: Partial<{
    initial: PickedSkill[];
    canAdd: boolean;
    onSave: (p: PickedSkill[]) => void;
  }> = {},
) {
  const onSave = props.onSave ?? vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SkillPickerDialog
        open
        onOpenChange={() => {}}
        opportunityId="o"
        initial={props.initial ?? []}
        canAdd={props.canAdd ?? true}
        saving={false}
        error=""
        onSave={onSave}
      />
    </QueryClientProvider>,
  );
  return { onSave };
}

const selected = () => screen.getByLabelText('Selected skills');
const chip = (name: string) => screen.getByRole('button', { name });
const search = (text: string) =>
  fireEvent.change(screen.getByPlaceholderText('Search or add a skill...'), {
    target: { value: text },
  });

beforeEach(() => {
  api.mockReset();
  post.mockReset();
  api.mockImplementation((p: string) => Promise.resolve(server(p)));
});

describe('skill picker', () => {
  it('searches partially and ignoring case, on the server', async () => {
    setup();
    search('WELD');
    expect(await screen.findByText('1 match')).toBeInTheDocument();
    expect(chip('Welding')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Plumbing' })).toBeNull();
    expect(api.mock.calls.some(([p]) => String(p).includes('q=WELD'))).toBe(
      true,
    );
  });

  it('keeps the list open while several skills are chosen, then removes one', async () => {
    setup();
    search('i'); // matches several skills
    await screen.findByText(/matches/);
    fireEvent.click(chip('Plumbing'));
    fireEvent.click(chip('Tailoring'));
    expect(selected()).toHaveTextContent('Selected Skills (2)');
    expect(chip('Plumbing')).toHaveAttribute('aria-pressed', 'true');
    // still searching, results still shown
    expect(chip('Painting')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove Plumbing' }));
    expect(selected()).toHaveTextContent('Selected Skills (1)');
    expect(selected()).not.toHaveTextContent('Plumbing');
  });

  it('shows popular skills from the server and selects them once only', async () => {
    setup();
    expect(await screen.findByText('Popular skills')).toBeInTheDocument();
    const popular = screen.getAllByRole('button', { name: 'Welding' })[0];
    fireEvent.click(popular);
    fireEvent.click(screen.getAllByRole('button', { name: 'Welding' })[0]); // toggles off
    fireEvent.click(screen.getAllByRole('button', { name: 'Welding' })[0]);
    expect(selected()).toHaveTextContent('Selected Skills (1)');
  });

  it('expands and collapses a category and pages with See more / See less', async () => {
    setup();
    // The first category starts open with 6 of 8 skills.
    expect(
      await screen.findByRole('button', { name: 'Painting' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hairdressing' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Motor repair' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'See more' }));
    expect(
      await screen.findByRole('button', { name: 'Motor repair' }),
    ).toBeInTheDocument();
    // the second page was a server request with an offset, not everything at once
    expect(api.mock.calls.some(([p]) => String(p).includes('offset=6'))).toBe(
      true,
    );
    fireEvent.click(screen.getByRole('button', { name: 'See less' }));
    expect(screen.queryByRole('button', { name: 'Motor repair' })).toBeNull();
    // collapse the whole category
    const head = screen.getByRole('button', { name: /^Trades/ });
    fireEvent.click(head);
    expect(head).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: 'Plumbing' })).toBeNull();
  });

  it('only loads a category once it is opened', async () => {
    setup();
    await screen.findByRole('button', { name: 'Painting' });
    expect(
      api.mock.calls.some(([p]) => String(p).includes('category=Office')),
    ).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /^Office/ }));
    expect(
      await screen.findByRole('button', { name: 'Bookkeeping' }),
    ).toBeInTheDocument();
  });

  it('offers to add a skill that does not exist, with a category, and selects it', async () => {
    post.mockResolvedValue(row('new1', 'Beekeeping', 'Other'));
    setup();
    search('Beekeeping');
    fireEvent.click(
      await screen.findByRole('button', { name: /Add “Beekeeping”/ }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Add skill' }));
    await waitFor(() => expect(selected()).toHaveTextContent('Beekeeping'));
    expect(post).toHaveBeenCalledWith('/requirement-skills/add', {
      name: 'Beekeeping',
      category: 'Other',
      confirm_similar: false,
    });
  });

  it('does not offer to add when the exact skill exists, or when the user may not add', async () => {
    setup({ canAdd: false });
    search('Welding');
    await screen.findByText('1 match');
    expect(screen.queryByRole('button', { name: /Add “/ })).toBeNull();
    search('Nothing at all');
    expect(await screen.findByText(/No skill matches/)).toBeInTheDocument();
    expect(screen.getByText(/Ask someone who edits/)).toBeInTheDocument();
  });

  it('stops a look-alike twin: shows similar skills and adds only when confirmed', async () => {
    const { ApiError } = await import('@/lib/api');
    post.mockRejectedValueOnce(
      new ApiError(409, 'Similar', [{ code: 'similar' }], '', {
        similar: [row('t0', 'Welding')],
      }),
    );
    post.mockResolvedValueOnce(row('n2', 'Weld repair', 'Trades'));
    setup();
    search('Weld repair');
    fireEvent.click(
      await screen.findByRole('button', { name: /Add “Weld repair”/ }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Add skill' }));
    expect(
      await screen.findByText(/Similar skills already exist/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add mine anyway' }));
    await waitFor(() => expect(selected()).toHaveTextContent('Weld repair'));
    expect(post).toHaveBeenLastCalledWith('/requirement-skills/add', {
      name: 'Weld repair',
      category: 'Other',
      confirm_similar: true,
    });
  });

  it('uses the existing skill instead of making a duplicate', async () => {
    const { ApiError } = await import('@/lib/api');
    post.mockRejectedValueOnce(
      new ApiError(409, 'Exists', [{ code: 'exists' }], '', {
        existing: row('t0', 'Welding'),
      }),
    );
    setup();
    search('welding!');
    fireEvent.click(
      await screen.findByRole('button', { name: /Add “welding!”/ }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Add skill' }));
    await waitFor(() => expect(selected()).toHaveTextContent('Welding'));
    expect(selected()).toHaveTextContent('Selected Skills (1)');
  });

  it('starts from the saved skills and sends ids with the must-have flag on save', async () => {
    const { onSave } = setup({
      initial: [{ id: 't0', name: 'Welding', mandatory: false }],
    });
    expect(selected()).toHaveTextContent('Welding');
    fireEvent.click(screen.getByLabelText('Must have'));
    fireEvent.click(await screen.findByRole('button', { name: 'Plumbing' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save skills' }));
    expect(onSave).toHaveBeenCalledWith([
      { id: 't0', name: 'Welding', mandatory: true },
      { id: 't1', name: 'Plumbing', mandatory: false },
    ]);
  });
});
