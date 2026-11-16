import { useState } from 'react';
import type { Member, RoleOption } from '@/pages/employer/employer-types';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
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

export interface Person {
  id: string;
  name: string;
  role: string;
  email: string;
  phone: string;
  is_primary: boolean;
  access: Member | null;
}

const STATE: Record<
  Member['state'],
  {
    label: string;
    variant: 'success' | 'warning' | 'destructive' | 'secondary';
  }
> = {
  active: { label: 'Can sign in', variant: 'success' },
  pending: { label: 'Invited', variant: 'warning' },
  expired: { label: 'Invite expired', variant: 'destructive' },
  suspended: { label: 'Suspended', variant: 'secondary' },
};

/** Where one list of people lives, and what else changes when it does. Staff reach any employer's
 * people by id; a company reaches only its own, so its paths carry no id. */
export interface PeopleEndpoints {
  people: string;
  contacts: string;
  access: string;
  /** Other queries to refresh after a change (the employer's page, its history, the dashboard). */
  alsoRefresh: string[][];
}

export const staffEndpoints = (employerId: string): PeopleEndpoints => ({
  people: `/employers/${employerId}/people`,
  contacts: `/employers/${employerId}/contacts`,
  access: `/employers/${employerId}/users`,
  alsoRefresh: [
    ['employer', employerId],
    ['employer-history', employerId],
  ],
});

export const COMPANY_ENDPOINTS: PeopleEndpoints = {
  people: '/employer/people',
  contacts: '/employer/contacts',
  access: '/employer/staff',
  alsoRefresh: [['employer-profile'], ['employer-dashboard']],
};

const day = (iso: string | null) => (iso ? iso.slice(0, 10) : '');
const BLANK = {
  name: '',
  role: '',
  email: '',
  phone: '',
  is_primary: false,
  sign_in: false,
  role_id: '',
};

/**
 * Everyone at one employer, as one list. A person is a single record (name, role, e-mail, phone);
 * if they can sign in to the employer portal, their access sits on the same row, with its role,
 * status and actions. Staff with `employers.edit` change the details; staff with
 * `employers.invite_user` give, change and take away access. The server enforces both.
 */
export function PeoplePanel({
  endpoints,
  canEdit,
  canAccess,
  description = "Everyone to reach at this employer. A person can also be given access to the employer portal, to manage the company's opportunities and referrals.",
  noun = 'employer',
  showAccess = true,
}: {
  endpoints: PeopleEndpoints;
  canEdit: boolean;
  canAccess: boolean;
  description?: string;
  /** "employer" for staff, "company" for the company's own admins. */
  noun?: string;
  /** Whether the sign-in columns are shown. A company's non-admins do not see who can sign in. */
  showAccess?: boolean;
}) {
  const qc = useQueryClient();
  const key = ['people', endpoints.people];
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: key });
    for (const k of endpoints.alsoRefresh)
      void qc.invalidateQueries({ queryKey: k });
  };
  const q = useQuery({
    queryKey: key,
    queryFn: () =>
      api<{ people: Person[]; roles: RoleOption[] }>(endpoints.people),
  });
  const roles = q.data?.roles ?? [];
  const roleOptions = roles.map((r) => ({ id: String(r.id), name: r.name }));

  const [form, setForm] = useState(BLANK);
  const [editing, setEditing] = useState<Person | 'new' | null>(null);
  const [granting, setGranting] = useState<Person | null>(null);
  const [roleFor, setRoleFor] = useState<Person | null>(null);
  const [role, setRole] = useState('');
  const [suspending, setSuspending] = useState<Person | null>(null);
  const [withdrawing, setWithdrawing] = useState<Person | null>(null);
  const [removing, setRemoving] = useState<Person | null>(null);
  const [error, setError] = useState('');
  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'Something went wrong.');
  const pickedId = granting ? form.role_id : roleFor ? role : form.role_id;
  const picked = roles.find((r) => String(r.id) === pickedId);

  const closeAll = () => {
    setEditing(null);
    setGranting(null);
    setRoleFor(null);
    setSuspending(null);
    setError('');
  };
  const invite = (p: Pick<Person, 'name' | 'email'>, extra: object) =>
    post(endpoints.access, {
      full_name: p.name,
      email: p.email,
      job_title: form.role,
      role_id: Number(form.role_id),
      ...extra,
    });

  const saveDetails = useMutation({
    mutationFn: async () => {
      const details = {
        name: form.name,
        role: form.role,
        phone: form.phone,
        is_primary: form.is_primary,
      };
      if (editing === 'new') {
        if (form.sign_in) {
          return invite(
            { name: form.name, email: form.email },
            { phone: form.phone, is_primary: form.is_primary },
          );
        }
        return post(endpoints.contacts, {
          ...details,
          email: form.email,
        });
      }
      // A person who can sign in keeps their sign-in address: it is not sent.
      const body = editing?.access
        ? details
        : { ...details, email: form.email };
      return api(`${endpoints.contacts}/${editing?.id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      toast.success(
        editing === 'new' && form.sign_in ? 'Invitation sent.' : 'Saved.',
      );
      closeAll();
      refresh();
    },
    onError: fail,
  });
  const giveAccess = useMutation({
    mutationFn: () =>
      invite(granting as Person, { contact_id: (granting as Person).id }),
    onSuccess: () => {
      toast.success('Invitation sent.');
      closeAll();
      refresh();
    },
    onError: fail,
  });
  const patchAccess = useMutation({
    mutationFn: ({ p, body }: { p: Person; body: object }) =>
      api(`${endpoints.access}/${p.access?.id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      toast.success('Saved.');
      closeAll();
      refresh();
    },
    onError: (e) => {
      fail(e);
      toast.error(e instanceof ApiError ? e.message : 'Could not save.');
    },
  });
  const withdraw = useMutation({
    mutationFn: (p: Person) =>
      api(`${endpoints.access}/${p.access?.id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      toast.success('Invitation withdrawn.');
      refresh();
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : 'Could not withdraw.'),
  });
  const remove = useMutation({
    mutationFn: (p: Person) =>
      api(`${endpoints.contacts}/${p.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Person removed.');
      refresh();
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : 'Could not remove.'),
  });

  const people = q.data?.people ?? [];
  const showActions = canEdit || canAccess;
  const editingPerson = editing && editing !== 'new' ? editing : null;
  const lockedEmail = !!editingPerson?.access;

  return (
    <Section
      title="People"
      description={description}
      flush
      action={
        canEdit && (
          <Button
            size="sm"
            onClick={() => {
              setForm(BLANK);
              setError('');
              setEditing('new');
            }}
          >
            <Plus /> Add person
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
      {q.data && people.length === 0 && (
        <div className="p-5">
          <EmptyState
            title="No people recorded yet"
            hint={
              canEdit
                ? 'Add the first person. You can give them portal access when you add them.'
                : undefined
            }
          />
        </div>
      )}
      {people.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Person</TableHead>
                <TableHead>Phone</TableHead>
                {showAccess && <TableHead>Portal access</TableHead>}
                {showAccess && <TableHead>Last sign-in</TableHead>}
                {showActions && (
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {people.map((p) => {
                const a = p.access;
                const s = a ? STATE[a.state] : null;
                return (
                  <TableRow key={p.id}>
                    <TableCell>
                      <p className="font-medium">
                        {p.name}
                        {p.is_primary && (
                          <span className="ml-1 text-xs font-normal text-muted-foreground">
                            (primary)
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {[p.role, p.email].filter(Boolean).join(' · ')}
                      </p>
                    </TableCell>
                    <TableCell>{p.phone || '—'}</TableCell>
                    {showAccess && (
                      <TableCell className="space-x-2">
                        {a && s ? (
                          <>
                            <Badge
                              variant={s.variant}
                              appearance="light"
                              className="whitespace-nowrap"
                            >
                              {s.label}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {a.roles.join(', ')}
                            </span>
                          </>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            No access
                          </span>
                        )}
                      </TableCell>
                    )}
                    {showAccess && (
                      <TableCell>{a ? day(a.last_login) : ''}</TableCell>
                    )}
                    {showActions && (
                      <TableCell>
                        <div className="flex flex-wrap justify-end gap-1">
                          {canEdit && (
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={`Edit ${p.name}`}
                              onClick={() => {
                                setForm({
                                  ...BLANK,
                                  name: p.name,
                                  role: p.role,
                                  email: p.email,
                                  phone: p.phone,
                                  is_primary: p.is_primary,
                                });
                                setError('');
                                setEditing(p);
                              }}
                            >
                              <Pencil /> Edit
                            </Button>
                          )}
                          {canAccess && !a && p.email && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setForm({ ...BLANK, role: p.role });
                                setError('');
                                setGranting(p);
                              }}
                            >
                              Give access
                            </Button>
                          )}
                          {canAccess &&
                            a &&
                            (a.state === 'active' ||
                              a.state === 'suspended') && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setRole('');
                                    setError('');
                                    setRoleFor(p);
                                  }}
                                >
                                  Change role
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() =>
                                    a.state === 'active'
                                      ? setSuspending(p)
                                      : patchAccess.mutate({
                                          p,
                                          body: { active: true },
                                        })
                                  }
                                >
                                  {a.state === 'active'
                                    ? 'Suspend'
                                    : 'Reactivate'}
                                </Button>
                              </>
                            )}
                          {canAccess &&
                            a &&
                            (a.state === 'pending' ||
                              a.state === 'expired') && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setWithdrawing(p)}
                              >
                                Withdraw invite
                              </Button>
                            )}
                          {canEdit && !a && (
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={`Remove ${p.name}`}
                              onClick={() => setRemoving(p)}
                            >
                              <Trash2 />
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
        open={editing !== null}
        onOpenChange={(o) => !o && closeAll()}
        title={editing === 'new' ? 'Add a person' : 'Edit person'}
        description="Their details, and (optionally) access to the employer portal."
        submitLabel={
          editing === 'new' && form.sign_in ? 'Add and invite' : 'Save'
        }
        pending={saveDetails.isPending}
        error={error}
        onSubmit={() => {
          if (!form.name.trim()) return setError('Enter their name.');
          if (editing === 'new' && form.sign_in) {
            if (!form.email.trim())
              return setError('Enter their email to invite them.');
            if (!form.role_id) return setError('Choose a portal role.');
          }
          setError('');
          saveDetails.mutate();
        }}
      >
        {(
          [
            ['name', 'Name', 'text'],
            ['role', 'Role / job title', 'text'],
            ['email', 'Email', 'email'],
            ['phone', 'Phone', 'tel'],
          ] as const
        ).map(([k, label, type]) => (
          <div key={k} className="space-y-1.5">
            <Label htmlFor={`person-${k}`}>
              {label}
              {k === 'name' && <span className="text-destructive"> *</span>}
            </Label>
            <Input
              id={`person-${k}`}
              type={type}
              value={form[k]}
              disabled={k === 'email' && lockedEmail}
              onChange={(ev) => setForm({ ...form, [k]: ev.target.value })}
            />
            {k === 'email' && lockedEmail && (
              <p className="text-xs text-muted-foreground">
                This is their sign-in name, so it is kept as it is.
              </p>
            )}
          </div>
        ))}
        <div className="flex items-center gap-2">
          <Checkbox
            id="person-primary"
            checked={form.is_primary}
            onCheckedChange={(c) =>
              setForm({ ...form, is_primary: c === true })
            }
          />
          <Label htmlFor="person-primary">Primary contact</Label>
        </div>
        {editing === 'new' && canAccess && (
          <div className="space-y-3 rounded-md border p-3">
            <div className="flex items-center gap-2">
              <Checkbox
                id="person-signin"
                checked={form.sign_in}
                onCheckedChange={(c) =>
                  setForm({ ...form, sign_in: c === true })
                }
              />
              <Label htmlFor="person-signin">
                Give access to the employer portal
              </Label>
            </div>
            {form.sign_in && (
              <div className="space-y-1.5">
                <Label>Portal role</Label>
                <SelectField
                  label="Choose a role"
                  value={form.role_id}
                  options={roleOptions}
                  onChange={(v) => setForm({ ...form, role_id: v })}
                />
                {picked && (
                  <p className="text-xs text-muted-foreground">
                    {picked.description}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  They get an email with a link to set a password.
                </p>
              </div>
            )}
          </div>
        )}
      </FormModal>

      <FormModal
        open={granting !== null}
        onOpenChange={(o) => !o && closeAll()}
        title={granting ? `Give ${granting.name} portal access` : ''}
        description={
          granting
            ? `They get an email at ${granting.email} with a link to set a password.`
            : ''
        }
        submitLabel="Send invitation"
        pending={giveAccess.isPending}
        error={error}
        onSubmit={() => {
          if (!form.role_id) return setError('Choose a role.');
          setError('');
          giveAccess.mutate();
        }}
      >
        <SelectField
          label="Choose a role"
          value={form.role_id}
          options={roleOptions}
          onChange={(v) => setForm({ ...form, role_id: v })}
        />
        {picked && (
          <p className="text-xs text-muted-foreground">{picked.description}</p>
        )}
      </FormModal>

      <FormModal
        open={roleFor !== null}
        onOpenChange={(o) => !o && closeAll()}
        title={roleFor ? `Change role for ${roleFor.name}` : ''}
        submitLabel="Save role"
        pending={patchAccess.isPending}
        error={error}
        onSubmit={() => {
          if (!role) return setError('Choose a role.');
          if (roleFor)
            patchAccess.mutate({ p: roleFor, body: { role_id: Number(role) } });
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
        open={suspending !== null}
        onOpenChange={(o) => !o && setSuspending(null)}
        title={suspending ? `Suspend ${suspending.name}?` : ''}
        description="They are signed out and cannot sign in until you reactivate them. Their work stays."
        confirmLabel="Suspend"
        onConfirm={() =>
          suspending &&
          patchAccess.mutate({ p: suspending, body: { active: false } })
        }
      />
      <ConfirmDialog
        open={withdrawing !== null}
        onOpenChange={(o) => !o && setWithdrawing(null)}
        title={
          withdrawing ? `Withdraw the invitation to ${withdrawing.email}?` : ''
        }
        description="The link in their email stops working. They stay on the list, without access, and you can invite them again later."
        confirmLabel="Withdraw"
        onConfirm={() => withdrawing && withdraw.mutate(withdrawing)}
      />
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Remove this person?"
        description={`${removing?.name ?? ''} will be removed from this ${noun}. The removal is kept in the activity history.`}
        onConfirm={() => removing && remove.mutate(removing)}
      />
    </Section>
  );
}
