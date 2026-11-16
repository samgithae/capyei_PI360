import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Section } from '@/components/shared/info-card';
import { ConfirmDialog, FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { Member, RoleOption } from './employer-types';

const STATE: Record<
  Member['state'],
  {
    label: string;
    variant: 'success' | 'warning' | 'destructive' | 'secondary';
  }
> = {
  active: { label: 'Active', variant: 'success' },
  pending: { label: 'Invited', variant: 'warning' },
  expired: { label: 'Invite expired', variant: 'destructive' },
  suspended: { label: 'Suspended', variant: 'secondary' },
};

const day = (iso: string | null) => (iso ? iso.slice(0, 10) : '');

interface Team {
  users: Member[];
  roles: RoleOption[];
}

/**
 * The people who can sign in for one company: invite, change role, suspend or reactivate, and
 * withdraw an invite. The company's own admins use `/employer/staff`; PI staff use
 * `/employers/<id>/users`. Both return the same rows, so one panel serves both and the two
 * cannot drift apart. The server enforces who may do what; the panel only hides what it cannot do.
 */
export function TeamPanel({
  base,
  rolesPath,
  title = 'Team',
  description,
  canManage = true,
}: {
  /** `/employer/staff` or `/employers/<id>/users`. */
  base: string;
  /** Where the role list is read when `base` returns bare rows (the company's own route). */
  rolesPath?: string;
  title?: string;
  description?: string;
  canManage?: boolean;
}) {
  const qc = useQueryClient();
  const key = ['team', base];
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: key });
    void qc.invalidateQueries({ queryKey: ['employer-dashboard'] });
  };
  const q = useQuery({
    queryKey: key,
    queryFn: async (): Promise<Team> => {
      const rows = await api<
        Member[] | { users: Member[]; roles: RoleOption[] }
      >(base);
      if (!Array.isArray(rows)) return rows;
      const roles = rolesPath ? await api<RoleOption[]>(rolesPath) : [];
      return { users: rows, roles };
    },
  });
  const [inviting, setInviting] = useState(false);
  const [invite, setInvite] = useState({
    email: '',
    full_name: '',
    job_title: '',
    role_id: '',
  });
  const [roleFor, setRoleFor] = useState<Member | null>(null);
  const [role, setRole] = useState('');
  const [switching, setSwitching] = useState<Member | null>(null);
  const [withdrawing, setWithdrawing] = useState<Member | null>(null);
  const [error, setError] = useState('');
  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'Something went wrong.');

  const send = useMutation({
    mutationFn: () =>
      post(base, { ...invite, role_id: Number(invite.role_id) }),
    onSuccess: () => {
      toast.success('Invitation sent.');
      setInviting(false);
      refresh();
    },
    onError: fail,
  });
  const patch = useMutation({
    mutationFn: ({ m, body }: { m: Member; body: object }) =>
      api(`${base}/${m.id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: () => {
      toast.success('Saved.');
      setRoleFor(null);
      setSwitching(null);
      refresh();
    },
    onError: (e) => {
      fail(e);
      toast.error(e instanceof ApiError ? e.message : 'Could not save.');
    },
  });
  const withdraw = useMutation({
    mutationFn: (m: Member) => api(`${base}/${m.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Invitation withdrawn.');
      refresh();
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : 'Could not withdraw.'),
  });

  const roles = q.data?.roles ?? [];
  const roleOptions = roles.map((r) => ({ id: String(r.id), name: r.name }));
  const picked = roles.find(
    (r) => String(r.id) === (roleFor ? role : invite.role_id),
  );

  return (
    <Section
      title={title}
      description={description}
      flush
      action={
        canManage && (
          <Button
            size="sm"
            onClick={() => {
              setInvite({
                email: '',
                full_name: '',
                job_title: '',
                role_id: '',
              });
              setError('');
              setInviting(true);
            }}
          >
            <Plus /> Invite a colleague
          </Button>
        )
      }
    >
      {q.isError && (
        <div className="p-5">
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </div>
      )}
      {q.isPending && (
        <div className="p-5">
          <LoadingState />
        </div>
      )}
      {q.data && q.data.users.length === 0 && (
        <div className="p-5">
          <EmptyState
            title="No one has an account yet"
            hint="Invite the first person. They get an email to set a password."
          />
        </div>
      )}
      {q.data && q.data.users.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last sign-in</TableHead>
                {canManage && (
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.users.map((m) => {
                const s = STATE[m.state];
                return (
                  <TableRow key={m.id}>
                    <TableCell>
                      <p className="font-medium">{m.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {m.email}
                        {m.job_title ? ` · ${m.job_title}` : ''}
                      </p>
                    </TableCell>
                    <TableCell>{m.roles.join(', ')}</TableCell>
                    <TableCell className="space-x-2">
                      <Badge variant={s.variant} appearance="light">
                        {s.label}
                      </Badge>
                      {m.is_owner && (
                        <Badge variant="primary" appearance="light">
                          Main contact
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>{day(m.last_login)}</TableCell>
                    {canManage && (
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          {(m.state === 'active' ||
                            m.state === 'suspended') && (
                            <>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setRole('');
                                  setError('');
                                  setRoleFor(m);
                                }}
                              >
                                Change role
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  m.state === 'active'
                                    ? setSwitching(m)
                                    : patch.mutate({
                                        m,
                                        body: { active: true },
                                      })
                                }
                              >
                                {m.state === 'active'
                                  ? 'Suspend'
                                  : 'Reactivate'}
                              </Button>
                            </>
                          )}
                          {(m.state === 'pending' || m.state === 'expired') && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setWithdrawing(m)}
                            >
                              Withdraw invite
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <FormModal
        open={inviting}
        onOpenChange={setInviting}
        title="Invite a colleague"
        description="They get an email with a link to set a password. The link works for a limited time."
        submitLabel="Send invitation"
        pending={send.isPending}
        error={error}
        onSubmit={() => {
          if (!invite.full_name.trim()) return setError('Enter their name.');
          if (!invite.email.trim()) return setError('Enter their email.');
          if (!invite.role_id) return setError('Choose a role.');
          setError('');
          send.mutate();
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="tm-name">Full name</Label>
          <Input
            id="tm-name"
            value={invite.full_name}
            onChange={(e) =>
              setInvite({ ...invite, full_name: e.target.value })
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tm-email">Email</Label>
          <Input
            id="tm-email"
            type="email"
            value={invite.email}
            onChange={(e) => setInvite({ ...invite, email: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tm-title">Job title (optional)</Label>
          <Input
            id="tm-title"
            value={invite.job_title}
            onChange={(e) =>
              setInvite({ ...invite, job_title: e.target.value })
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label>Role</Label>
          <SelectField
            label="Choose a role"
            value={invite.role_id}
            options={roleOptions}
            onChange={(v) => setInvite({ ...invite, role_id: v })}
          />
          {picked && (
            <p className="text-xs text-muted-foreground">
              {picked.description}
            </p>
          )}
        </div>
      </FormModal>

      <FormModal
        open={roleFor !== null}
        onOpenChange={(o) => !o && setRoleFor(null)}
        title={roleFor ? `Change role for ${roleFor.name}` : ''}
        submitLabel="Save role"
        pending={patch.isPending}
        error={error}
        onSubmit={() => {
          if (!role) return setError('Choose a role.');
          if (roleFor)
            patch.mutate({ m: roleFor, body: { role_id: Number(role) } });
        }}
      >
        <SelectField
          label="Choose a role"
          value={role}
          options={roleOptions}
          onChange={setRole}
        />
        {picked && (
          <p className="text-xs text-muted-foreground">{picked.description}</p>
        )}
      </FormModal>

      <ConfirmDialog
        open={switching !== null}
        onOpenChange={(o) => !o && setSwitching(null)}
        title={switching ? `Suspend ${switching.name}?` : ''}
        description="They are signed out and cannot sign in until you reactivate them. Their work stays."
        confirmLabel="Suspend"
        onConfirm={() =>
          switching && patch.mutate({ m: switching, body: { active: false } })
        }
      />
      <ConfirmDialog
        open={withdrawing !== null}
        onOpenChange={(o) => !o && setWithdrawing(null)}
        title={
          withdrawing ? `Withdraw the invitation to ${withdrawing.email}?` : ''
        }
        description="The link in their email stops working. You can invite them again later."
        confirmLabel="Withdraw"
        onConfirm={() => withdrawing && withdraw.mutate(withdrawing)}
      />
    </Section>
  );
}
