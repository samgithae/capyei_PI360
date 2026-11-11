import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
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
import { ActivityTimeline } from '@/components/shared/activity-timeline';
import { DetailList, Section } from '@/components/shared/info-card';
import {
  ConfirmDialog,
  DialogShell,
  FormModal,
} from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { EmployerForm, EmployerValues, Options } from './employer-form';

interface Contact {
  id: string;
  name: string;
  role: string;
  email: string;
  phone: string;
  is_primary: boolean;
}
interface Detail extends EmployerValues {
  id: string;
  sector: string;
  county: string;
  contacts: Contact[];
}
interface Event {
  at: string;
  actor: string;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}
interface OppRow {
  id: string;
  title: string;
  kind: string;
  status: string;
  positions: number;
  closing_date: string | null;
}

export function EmployerPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const canEdit = can('employers.edit');
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Contact | null>(null);
  const [contact, setContact] = useState({
    name: '',
    role: '',
    email: '',
    phone: '',
  });
  const [contactError, setContactError] = useState('');

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['employer', id] });
    void qc.invalidateQueries({ queryKey: ['employer-history', id] });
  };
  const q = useQuery({
    queryKey: ['employer', id],
    queryFn: () => api<Detail>(`/employers/${id}`),
    retry: false,
  });
  const history = useQuery({
    queryKey: ['employer-history', id],
    queryFn: () => api<Event[]>(`/employers/${id}/history`),
  });
  const opps = useQuery({
    queryKey: ['employer-opportunities', id],
    queryFn: () =>
      api<{ total: number; results: OppRow[] }>(
        `/opportunities?employer=${id}`,
      ),
  });
  const options = useQuery({
    queryKey: ['employer-filters'],
    queryFn: () => api<Options>('/employers/filters'),
    enabled: editing,
  });
  const save = useMutation({
    mutationFn: ({ v, confirm }: { v: EmployerValues; confirm: boolean }) =>
      api(`/employers/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ ...v, confirm_duplicate: confirm }),
      }),
    onSuccess: () => {
      setEditing(false);
      toast.success('Employer updated.');
      refresh();
    },
  });
  const addContact = useMutation({
    mutationFn: () => post(`/employers/${id}/contacts`, contact),
    onSuccess: () => {
      setContact({ name: '', role: '', email: '', phone: '' });
      setContactError('');
      setAdding(false);
      toast.success('Contact added.');
      refresh();
    },
    onError: (e) =>
      setContactError(e instanceof ApiError ? e.message : 'Could not add.'),
  });
  const removeContact = useMutation({
    mutationFn: (cid: string) =>
      api(`/employers/${id}/contacts/${cid}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Contact removed.');
      refresh();
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : 'Could not remove.'),
  });

  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Employer not found"
            hint="It may have been removed or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        <Link className="text-primary" to="/employers">
          Back to employers
        </Link>
      </div>
    );
  }
  const e = q.data;
  if (!e) return <LoadingState />;

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{e.name} | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Employers', to: '/employers' }, { label: e.name }]}
        title={e.name}
        badges={<StatusBadge status={e.status} />}
        meta={
          <>
            {e.sector && <span>{e.sector}</span>}
            {e.county && <span>{e.county}</span>}
          </>
        }
        actions={
          canEdit && (
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil /> Edit employer
            </Button>
          )
        }
      />

      {editing && (
        <DialogShell
          open
          onOpenChange={(o) => !o && setEditing(false)}
          title="Edit employer"
        >
          <EmployerForm
            initial={{
              name: e.name,
              sector_id: e.sector_id,
              county_id: e.county_id,
              sub_county: e.sub_county,
              address: e.address,
              website: e.website,
              status: e.status,
              notes: e.notes,
            }}
            employerId={e.id}
            options={options.data}
            onCancel={() => setEditing(false)}
            onSave={async (v, confirm) => {
              await save.mutateAsync({ v, confirm });
            }}
          />
        </DialogShell>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Section title="Employer information">
            <DetailList
              items={[
                { label: 'Status', value: <StatusBadge status={e.status} /> },
                { label: 'Industry', value: e.sector },
                { label: 'County', value: e.county },
                { label: 'Sub-county', value: e.sub_county },
                { label: 'Address', value: e.address },
                {
                  label: 'Website',
                  value: e.website,
                },
                { label: 'Notes', value: e.notes },
              ]}
            />
          </Section>

          <Section
            title="Contacts"
            description="People to reach at this employer."
            flush
            action={
              canEdit && (
                <Button size="sm" onClick={() => setAdding(true)}>
                  <Plus /> Add contact
                </Button>
              )
            }
          >
            {e.contacts.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No contacts yet"
                  hint={canEdit ? 'Use Add contact to record one.' : undefined}
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead>Name</TableHead>
                      <TableHead>Role</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Phone</TableHead>
                      {canEdit && (
                        <TableHead className="w-16">
                          <span className="sr-only">Actions</span>
                        </TableHead>
                      )}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {e.contacts.map((c) => (
                      <TableRow key={c.id}>
                        <TableCell className="font-medium">
                          {c.name}
                          {c.is_primary && (
                            <span className="ms-2 text-xs text-muted-foreground">
                              (primary)
                            </span>
                          )}
                        </TableCell>
                        <TableCell>{c.role}</TableCell>
                        <TableCell>{c.email}</TableCell>
                        <TableCell>{c.phone}</TableCell>
                        {canEdit && (
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={`Remove ${c.name}`}
                              onClick={() => setRemoving(c)}
                            >
                              <Trash2 />
                            </Button>
                          </TableCell>
                        )}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </Section>

          {(opps.data?.results.length ?? 0) > 0 && (
            <Section
              title="Opportunities"
              description={`${opps.data?.total} from this employer`}
              flush
            >
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead>Title</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Positions</TableHead>
                      <TableHead>Closes</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {opps.data?.results.map((o) => (
                      <TableRow key={o.id}>
                        <TableCell>
                          <Link
                            className="font-medium hover:text-primary"
                            to={`/opportunities/${o.id}`}
                          >
                            {o.title}
                          </Link>
                        </TableCell>
                        <TableCell className="capitalize">{o.kind}</TableCell>
                        <TableCell>{o.positions}</TableCell>
                        <TableCell>{o.closing_date ?? ''}</TableCell>
                        <TableCell>
                          <StatusBadge status={o.status} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </Section>
          )}
        </div>

        <Section title="Activity">
          {history.isPending ? (
            <LoadingState rows={3} />
          ) : (
            <ActivityTimeline events={history.data ?? []} />
          )}
        </Section>
      </div>

      <FormModal
        open={adding}
        onOpenChange={(o) => {
          setAdding(o);
          if (!o) setContactError('');
        }}
        title="Add contact"
        description="Record a person to reach at this employer."
        submitLabel="Add contact"
        pending={addContact.isPending}
        error={contactError}
        onSubmit={() => addContact.mutate()}
      >
        {(
          [
            ['name', 'Name', true, 'text'],
            ['role', 'Role', false, 'text'],
            ['email', 'Email', false, 'email'],
            ['phone', 'Phone', false, 'tel'],
          ] as const
        ).map(([k, label, required, type]) => (
          <div key={k} className="space-y-1.5">
            <Label htmlFor={`contact-${k}`}>
              {label}
              {required && <span className="text-destructive"> *</span>}
            </Label>
            <Input
              id={`contact-${k}`}
              type={type}
              required={required}
              value={contact[k]}
              onChange={(ev) =>
                setContact({ ...contact, [k]: ev.target.value })
              }
            />
          </div>
        ))}
      </FormModal>

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Remove this contact?"
        description={`${removing?.name ?? ''} will be removed from this employer. The removal is kept in the activity history.`}
        onConfirm={() => removing && removeContact.mutate(removing.id)}
      />
    </div>
  );
}
