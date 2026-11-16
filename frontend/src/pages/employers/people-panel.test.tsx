import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { COMPANY_ENDPOINTS, PeoplePanel, staffEndpoints } from './people-panel';

// jsdom has no ResizeObserver, which the Radix checkbox measures with.
vi.stubGlobal(
  'ResizeObserver',
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: (...a: unknown[]) => api(...a),
  ApiError: class extends Error {},
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const access = (over: object) => ({
  id: 'm1',
  name: 'Wanjiru Boss',
  email: 'boss@acme.example',
  job_title: 'Director',
  is_owner: true,
  state: 'active',
  roles: ['Company admin'],
  invited_at: null,
  expires_at: null,
  last_login: null,
  ...over,
});
const person = (over: object) => ({
  id: 'c1',
  name: 'Wanjiru Boss',
  role: 'Director',
  email: 'boss@acme.example',
  phone: '0700',
  is_primary: true,
  access: access({}),
  ...over,
});
const PEOPLE = [
  person({}),
  person({
    id: 'c2',
    name: 'Otieno HR',
    email: 'hr@acme.example',
    is_primary: false,
    access: access({ id: 'm2', state: 'pending', roles: ['HR / Recruiter'] }),
  }),
  person({
    id: 'c3',
    name: 'Njeri Plain',
    email: 'njeri@acme.example',
    is_primary: false,
    access: null,
  }),
];
const ROLES = [{ id: 1, name: 'HR / Recruiter', description: 'Posts jobs' }];

function show(canEdit = true, canAccess = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PeoplePanel
        endpoints={staffEndpoints('e1')}
        canEdit={canEdit}
        canAccess={canAccess}
      />
    </QueryClientProvider>,
  );
}

describe('PeoplePanel', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockResolvedValue({ people: PEOPLE, roles: ROLES });
  });

  it('shows each person once, with their access on the same row', async () => {
    show();
    expect(await screen.findByText('Njeri Plain')).toBeTruthy();
    expect(screen.getAllByText('Wanjiru Boss')).toHaveLength(1);
    expect(screen.getByText('Can sign in')).toBeTruthy();
    expect(screen.getByText('Invited')).toBeTruthy();
    expect(screen.getByText('No access')).toBeTruthy();
  });

  it('offers the action that fits each person', async () => {
    show();
    await screen.findByText('Njeri Plain');
    expect(screen.getAllByText('Give access')).toHaveLength(1);
    expect(screen.getAllByText('Suspend')).toHaveLength(1);
    expect(screen.getAllByText('Withdraw invite')).toHaveLength(1);
    // Only a person without access can be removed.
    expect(screen.queryByLabelText('Remove Wanjiru Boss')).toBeNull();
    expect(screen.getByLabelText('Remove Njeri Plain')).toBeTruthy();
  });

  it('hides account controls from staff who may only edit details', async () => {
    show(true, false);
    await screen.findByText('Njeri Plain');
    expect(screen.queryByText('Give access')).toBeNull();
    expect(screen.queryByText('Suspend')).toBeNull();
    expect(screen.getByText('Add person')).toBeTruthy();
  });

  it('hides every control from a reader who may not edit', async () => {
    show(false, false);
    await screen.findByText('Njeri Plain');
    expect(screen.queryByText('Add person')).toBeNull();
    expect(screen.queryByLabelText('Edit Njeri Plain')).toBeNull();
  });

  it('adds a plain person without inviting them', async () => {
    show();
    await screen.findByText('Njeri Plain');
    fireEvent.click(screen.getByText('Add person'));
    fireEvent.change(await screen.findByLabelText(/Name/), {
      target: { value: 'Kamau' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        '/employers/e1/contacts',
        expect.objectContaining({ name: 'Kamau' }),
      ),
    );
  });

  it('asks for an email and a role before adding with access', async () => {
    show();
    await screen.findByText('Njeri Plain');
    fireEvent.click(screen.getByText('Add person'));
    fireEvent.change(await screen.findByLabelText(/Name/), {
      target: { value: 'Kamau' },
    });
    fireEvent.click(
      screen.getByLabelText('Give access to the employer portal'),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Add and invite' }));
    await waitFor(() =>
      expect(
        screen.getByText('Enter their email to invite them.'),
      ).toBeTruthy(),
    );
    expect(api.mock.calls.some((c) => c[0] === '/employers/e1/users')).toBe(
      false,
    );
  });

  it('keeps the sign-in email fixed for a person who can sign in', async () => {
    show();
    await screen.findByText('Njeri Plain');
    fireEvent.click(screen.getByLabelText('Edit Wanjiru Boss'));
    const email = (await screen.findByLabelText('Email')) as HTMLInputElement;
    expect(email.disabled).toBe(true);
    expect(screen.getByText(/sign-in name/)).toBeTruthy();
  });

  it("uses the company's own paths, with no employer id", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <PeoplePanel
          endpoints={COMPANY_ENDPOINTS}
          noun="company"
          canEdit
          canAccess
        />
      </QueryClientProvider>,
    );
    await screen.findByText('Njeri Plain');
    expect(api).toHaveBeenCalledWith('/employer/people');
    fireEvent.click(screen.getByLabelText('Remove Njeri Plain'));
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith('/employer/contacts/c3', {
        method: 'DELETE',
      }),
    );
  });

  it('hides who can sign in from someone who may not manage the team', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    api.mockResolvedValue({
      people: PEOPLE.map((p) => ({ ...p, access: null })),
      roles: [],
    });
    render(
      <QueryClientProvider client={qc}>
        <PeoplePanel
          endpoints={COMPANY_ENDPOINTS}
          noun="company"
          canEdit={false}
          canAccess={false}
          showAccess={false}
        />
      </QueryClientProvider>,
    );
    await screen.findByText('Njeri Plain');
    expect(screen.queryByText('Portal access')).toBeNull();
    expect(screen.queryByText('No access')).toBeNull();
    expect(screen.queryByText('Give access')).toBeNull();
  });
});
