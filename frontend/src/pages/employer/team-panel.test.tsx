import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TeamPanel } from './team-panel';

const api = vi.fn();
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => api(...a),
  post: (...a: unknown[]) => api(...a),
  ApiError: class extends Error {},
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const row = (over: object) => ({
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
const ROLES = [{ id: 1, name: 'HR / Recruiter', description: 'Posts jobs' }];

function show(props: Partial<Parameters<typeof TeamPanel>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TeamPanel
        base="/employer/staff"
        rolesPath="/employer/roles"
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe('TeamPanel', () => {
  beforeEach(() => {
    api.mockReset();
    api.mockImplementation((path: string) =>
      Promise.resolve(
        path === '/employer/roles'
          ? ROLES
          : [
              row({}),
              row({
                id: 'm2',
                name: 'Otieno HR',
                email: 'hr@acme.example',
                is_owner: false,
                state: 'pending',
                roles: ['HR / Recruiter'],
              }),
              row({
                id: 'm3',
                name: 'Njeri Away',
                email: 'njeri@acme.example',
                is_owner: false,
                state: 'suspended',
              }),
            ],
      ),
    );
  });

  it('offers the action that fits each person’s state', async () => {
    show();
    expect(await screen.findByText('Otieno HR')).toBeTruthy();
    expect(screen.getAllByText('Suspend')).toHaveLength(1);
    expect(screen.getAllByText('Reactivate')).toHaveLength(1);
    expect(screen.getAllByText('Withdraw invite')).toHaveLength(1);
    expect(screen.getByText('Invited')).toBeTruthy();
  });

  it('hides every control when the reader may not manage the team', async () => {
    show({ canManage: false });
    expect(await screen.findByText('Otieno HR')).toBeTruthy();
    expect(screen.queryByText('Invite a colleague')).toBeNull();
    expect(screen.queryByText('Suspend')).toBeNull();
  });

  it('asks for a role before sending an invitation', async () => {
    show();
    await screen.findByText('Otieno HR');
    fireEvent.click(screen.getByText('Invite a colleague'));
    fireEvent.change(await screen.findByLabelText('Full name'), {
      target: { value: 'New Person' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'new@acme.example' },
    });
    fireEvent.click(screen.getByText('Send invitation'));
    await waitFor(() =>
      expect(screen.getByText('Choose a role.')).toBeTruthy(),
    );
    expect(api.mock.calls.some((c) => c[1]?.role_id !== undefined)).toBe(false);
  });

  it('reads the staff shape too, where roles come with the rows', async () => {
    api.mockImplementation(() =>
      Promise.resolve({ users: [row({})], roles: ROLES }),
    );
    show({ base: '/employers/e1/users', rolesPath: undefined });
    expect(await screen.findByText('Wanjiru Boss')).toBeTruthy();
    expect(api).toHaveBeenCalledTimes(1);
  });
});
