import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarPageTitle,
} from '@/components/layouts/layout-1/components/toolbar';
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

export function EmployerPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const canEdit = can('employers.edit');
  const [editing, setEditing] = useState(false);
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
      refresh();
    },
  });
  const addContact = useMutation({
    mutationFn: () => post(`/employers/${id}/contacts`, contact),
    onSuccess: () => {
      setContact({ name: '', role: '', email: '', phone: '' });
      setContactError('');
      refresh();
    },
    onError: (e) =>
      setContactError(e instanceof ApiError ? e.message : 'Could not add.'),
  });
  const removeContact = useMutation({
    mutationFn: (cid: string) =>
      api(`/employers/${id}/contacts/${cid}`, { method: 'DELETE' }),
    onSuccess: refresh,
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

  const onAdd = (ev: FormEvent) => {
    ev.preventDefault();
    addContact.mutate();
  };

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{e.name} | PI 360</title>
      </Helmet>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarPageTitle>{e.name}</ToolbarPageTitle>
        </ToolbarHeading>
        {canEdit && !editing && (
          <Button variant="outline" onClick={() => setEditing(true)}>
            Edit
          </Button>
        )}
      </Toolbar>

      {editing ? (
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
      ) : (
        <div className="flex flex-wrap gap-3 text-sm">
          <Badge variant="secondary">{e.status}</Badge>
          {e.sector && <span>{e.sector}</span>}
          {e.county && <span>{e.county}</span>}
          {e.sub_county && <span>{e.sub_county}</span>}
          {e.address && <span>{e.address}</span>}
          {e.website && <span>{e.website}</span>}
          {e.notes && <span>{e.notes}</span>}
        </div>
      )}

      <section>
        <h2 className="mb-2 font-semibold">Contacts</h2>
        <ul className="space-y-1 text-sm">
          {e.contacts.map((c) => (
            <li key={c.id} className="flex items-center gap-3">
              <span>
                {c.name}
                {c.role && `, ${c.role}`} {c.email} {c.phone}
                {c.is_primary && ' (primary)'}
              </span>
              {canEdit && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => removeContact.mutate(c.id)}
                >
                  Remove
                </Button>
              )}
            </li>
          ))}
          {e.contacts.length === 0 && (
            <li className="text-muted-foreground">No contacts yet.</li>
          )}
        </ul>
        {canEdit && (
          <form onSubmit={onAdd} className="mt-3 flex flex-wrap gap-2">
            {(['name', 'role', 'email', 'phone'] as const).map((k) => (
              <Input
                key={k}
                aria-label={`Contact ${k}`}
                placeholder={k[0].toUpperCase() + k.slice(1)}
                value={contact[k]}
                required={k === 'name'}
                onChange={(ev) =>
                  setContact({ ...contact, [k]: ev.target.value })
                }
                className="w-40"
              />
            ))}
            <Button type="submit" disabled={addContact.isPending}>
              Add contact
            </Button>
          </form>
        )}
        {contactError && <p role="alert">{contactError}</p>}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">History</h2>
        <ul className="space-y-1 text-sm">
          {history.data?.map((h, i) => (
            <li key={i}>
              {new Date(h.at).toLocaleString()} - {h.actor}: {h.action}
            </li>
          ))}
        </ul>
      </section>
      <Link className="text-primary text-sm" to="/employers">
        Back to employers
      </Link>
    </div>
  );
}
