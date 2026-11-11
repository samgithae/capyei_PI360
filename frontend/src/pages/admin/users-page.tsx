import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input, InputWrapper } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { ErrorState, LoadingState } from '@/components/states';

interface StaffUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  mfa_enrolled: boolean;
  last_login: string | null;
  roles: { id: number; name: string; active: boolean }[];
}
interface Role {
  id: number;
  name: string;
  active: boolean;
}

type Action = 'suspend' | 'reactivate' | 'reset-mfa';
const LABEL: Record<Action, string> = {
  suspend: 'Suspend',
  reactivate: 'Reactivate',
  'reset-mfa': 'Reset MFA',
};

export function UsersPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [pending, setPending] = useState<{
    user: StaffUser;
    action: Action;
  } | null>(null);
  const [reason, setReason] = useState('');
  const [message, setMessage] = useState('');

  const users = useQuery({
    queryKey: ['users', q],
    queryFn: () =>
      api<StaffUser[]>(`/identity/users?q=${encodeURIComponent(q)}`),
  });
  const roles = useQuery({
    queryKey: ['roles'],
    queryFn: () => api<Role[]>('/identity/roles'),
    enabled: can('identity.manage_roles'),
  });

  const act = useMutation({
    mutationFn: ({ user, action }: { user: StaffUser; action: Action }) =>
      post(`/identity/users/${user.id}/${action}`, { reason }),
    onSuccess: () => {
      setPending(null);
      setReason('');
      setMessage('');
      void qc.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e) => setMessage(e instanceof ApiError ? e.message : 'Failed'),
  });

  const canManage = can('identity.manage_users');

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Staff accounts | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Staff accounts' }]}
        title="Staff accounts"
      />

      {canManage && <CreateUser roles={roles.data ?? []} />}

      {message && (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}

      <DataCard
        title="Staff"
        toolbar={
          <InputWrapper className="w-72">
            <Search />
            <Input
              placeholder="Search name, username or email"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Search staff"
            />
          </InputWrapper>
        }
      >
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead>Name</TableHead>
              <TableHead>Roles</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>MFA</TableHead>
              {canManage && <TableHead />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.data?.map((u) => (
              <TableRow key={u.id}>
                <TableCell>
                  <div className="font-medium">
                    {`${u.first_name} ${u.last_name}`.trim() || u.username}
                  </div>
                  <div className="text-muted-foreground">{u.email}</div>
                </TableCell>
                <TableCell>
                  {u.roles.map((r) => r.name).join(', ') || '—'}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={u.is_active ? 'success' : 'destructive'}
                    appearance="light"
                  >
                    {u.is_active ? 'Active' : 'Suspended'}
                  </Badge>
                </TableCell>
                <TableCell>
                  {u.mfa_enrolled ? 'Enrolled' : 'Not enrolled'}
                </TableCell>
                {canManage && (
                  <TableCell>
                    {(u.is_active
                      ? (['suspend', 'reset-mfa'] as Action[])
                      : (['reactivate'] as Action[])
                    ).map((action) => (
                      <Button
                        key={action}
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setPending({ user: u, action });
                          setMessage('');
                        }}
                      >
                        {LABEL[action]}
                      </Button>
                    ))}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </DataCard>
      {users.isError && (
        <ErrorState error={users.error} onRetry={() => users.refetch()} />
      )}
      {users.isPending && <LoadingState />}

      {pending && (
        <form
          className="rounded-md border p-4 space-y-3 max-w-md"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            act.mutate(pending);
          }}
        >
          <p className="text-sm">
            {LABEL[pending.action]} <strong>{pending.user.username}</strong>?
            This is recorded in the audit trail.
          </p>
          <Input
            placeholder="Reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            autoFocus
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={act.isPending}>
              Confirm
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setPending(null)}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

function CreateUser({ roles }: { roles: Role[] }) {
  const qc = useQueryClient();
  const empty = {
    username: '',
    email: '',
    first_name: '',
    last_name: '',
    role: '',
  };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState('');
  const create = useMutation({
    mutationFn: () =>
      post('/identity/users', {
        username: form.username,
        email: form.email,
        first_name: form.first_name,
        last_name: form.last_name,
        roles: form.role ? [Number(form.role)] : [],
      }),
    onSuccess: () => {
      setForm(empty);
      setError('');
      void qc.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Failed'),
  });
  const set = (k: keyof typeof empty) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <form
      className="rounded-md border p-4 grid gap-3 sm:grid-cols-2 max-w-2xl"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <h2 className="sm:col-span-2 font-medium">Add a staff account</h2>
      <Input
        placeholder="Username"
        value={form.username}
        onChange={set('username')}
        required
      />
      <Input
        type="email"
        placeholder="Email"
        value={form.email}
        onChange={set('email')}
        required
      />
      <Input
        placeholder="First name"
        value={form.first_name}
        onChange={set('first_name')}
      />
      <Input
        placeholder="Last name"
        value={form.last_name}
        onChange={set('last_name')}
      />
      {roles.length > 0 && (
        <SelectField
          label="Role"
          className="w-48"
          value={form.role}
          emptyLabel="No role yet"
          options={roles.filter((r) => r.active)}
          onChange={(x) => setForm({ ...form, role: x })}
        />
      )}
      {error && (
        <p role="alert" className="sm:col-span-2 text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="sm:col-span-2">
        <Button type="submit" disabled={create.isPending}>
          Create account
        </Button>
      </div>
    </form>
  );
}
