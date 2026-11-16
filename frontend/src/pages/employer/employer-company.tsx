import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
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
import { DetailList, Section } from '@/components/shared/info-card';
import { ConfirmDialog, FormModal } from '@/components/shared/modals';
import { MultiSelectField } from '@/components/shared/multi-select-field';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { Ref } from './employer-types';

interface Contact {
  id: string;
  name: string;
  role: string;
  email: string;
  phone: string;
  is_primary: boolean;
}
interface Profile {
  id: string;
  name: string;
  sectors: Ref[];
  counties: Ref[];
  sector_ids: string[];
  county_ids: string[];
  sub_county: string;
  address: string;
  website: string;
  contacts: Contact[];
  options: { sectors: Ref[]; counties: Ref[] };
}

const BLANK: Omit<Contact, 'id'> = {
  name: '',
  role: '',
  email: '',
  phone: '',
  is_primary: false,
};

export function EmployerCompanyPage() {
  const { can } = useAuth();
  const canEdit = can('employer.edit_profile');
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['employer-profile'] });
    // The opportunity form reads the same places.
    void qc.invalidateQueries({ queryKey: ['employer'] });
  };
  const q = useQuery({
    queryKey: ['employer-profile'],
    queryFn: () => api<Profile>('/employer/profile'),
  });
  const p = q.data;

  const [editing, setEditing] = useState(false);
  const [v, setV] = useState({
    sub_county: '',
    address: '',
    website: '',
    sector_ids: [] as string[],
    county_ids: [] as string[],
  });
  const [error, setError] = useState('');
  useEffect(() => {
    if (editing && p)
      setV({
        sub_county: p.sub_county,
        address: p.address,
        website: p.website,
        sector_ids: p.sector_ids,
        county_ids: p.county_ids,
      });
  }, [editing, p]);
  const save = useMutation({
    mutationFn: () =>
      api('/employer/profile', { method: 'PATCH', body: JSON.stringify(v) }),
    onSuccess: () => {
      toast.success('Company details saved.');
      setEditing(false);
      setError('');
      refresh();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  const [contact, setContact] = useState<Omit<Contact, 'id'>>(BLANK);
  const [contactId, setContactId] = useState<string | null>(null);
  const [contactOpen, setContactOpen] = useState(false);
  const [removing, setRemoving] = useState<Contact | null>(null);
  const [contactError, setContactError] = useState('');
  const saveContact = useMutation({
    mutationFn: () =>
      contactId
        ? api(`/employer/contacts/${contactId}`, {
            method: 'PATCH',
            body: JSON.stringify(contact),
          })
        : post('/employer/contacts', contact),
    onSuccess: () => {
      toast.success(contactId ? 'Contact updated.' : 'Contact added.');
      setContactOpen(false);
      refresh();
    },
    onError: (e) =>
      setContactError(e instanceof ApiError ? e.message : 'Could not save.'),
  });
  const removeContact = useMutation({
    mutationFn: (id: string) =>
      api(`/employer/contacts/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Contact removed.');
      refresh();
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : 'Could not remove.'),
  });

  if (q.isError)
    return (
      <div className="container-fluid">
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </div>
    );
  if (!p) return <LoadingState />;

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>Company profile | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Company profile' }]}
        title={p.name}
        description="What PI 360 knows about your company. To change the company name, contact PI 360."
        actions={
          canEdit && (
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil /> Edit details
            </Button>
          )
        }
      />
      <Section title="Details">
        <DetailList
          items={[
            { label: 'Company', value: p.name },
            {
              label: 'Industry / Sector',
              value: p.sectors.map((s) => s.name).join(', '),
            },
            {
              label: 'Counties',
              value: p.counties.map((c) => c.name).join(', '),
            },
            { label: 'Sub-county', value: p.sub_county },
            { label: 'Address', value: p.address },
            { label: 'Website', value: p.website },
          ]}
        />
      </Section>
      <Section
        title="Contacts"
        description="The people at your company PI 360 can reach."
        flush
        action={
          canEdit && (
            <Button
              size="sm"
              onClick={() => {
                setContactId(null);
                setContact(BLANK);
                setContactError('');
                setContactOpen(true);
              }}
            >
              <Plus /> Add contact
            </Button>
          )
        }
      >
        {p.contacts.length === 0 ? (
          <div className="p-5">
            <EmptyState title="No contacts yet" />
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
                    <TableHead>
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {p.contacts.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="space-x-2">
                      <span className="font-medium">{c.name}</span>
                      {c.is_primary && (
                        <Badge variant="primary" appearance="light">
                          Primary
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>{c.role}</TableCell>
                    <TableCell>{c.email}</TableCell>
                    <TableCell>{c.phone}</TableCell>
                    {canEdit && (
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`Edit ${c.name}`}
                            onClick={() => {
                              setContactId(c.id);
                              setContact({
                                name: c.name,
                                role: c.role,
                                email: c.email,
                                phone: c.phone,
                                is_primary: c.is_primary,
                              });
                              setContactError('');
                              setContactOpen(true);
                            }}
                          >
                            <Pencil />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`Remove ${c.name}`}
                            onClick={() => setRemoving(c)}
                          >
                            <Trash2 />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      <FormModal
        open={editing}
        onOpenChange={setEditing}
        title="Edit company details"
        description="Opportunities can only use the industries and counties listed here."
        pending={save.isPending}
        error={error}
        onSubmit={() => {
          setError('');
          save.mutate();
        }}
      >
        <div className="space-y-1.5">
          <Label>Industry / Sector</Label>
          <MultiSelectField
            label="Add an industry / sector"
            className="w-full"
            options={p.options.sectors}
            labels={p.sectors}
            value={v.sector_ids}
            onChange={(ids) => setV({ ...v, sector_ids: ids })}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Counties</Label>
          <MultiSelectField
            label="Add a county"
            className="w-full"
            options={p.options.counties}
            labels={p.counties}
            value={v.county_ids}
            onChange={(ids) => setV({ ...v, county_ids: ids, sub_county: '' })}
          />
        </div>
        {v.county_ids.length === 1 && (
          <div className="space-y-1.5">
            <Label htmlFor="ec-sub">Sub-county</Label>
            <Input
              id="ec-sub"
              value={v.sub_county}
              onChange={(e) => setV({ ...v, sub_county: e.target.value })}
            />
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="ec-address">Address</Label>
          <Input
            id="ec-address"
            value={v.address}
            onChange={(e) => setV({ ...v, address: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ec-web">Website</Label>
          <Input
            id="ec-web"
            type="url"
            placeholder="https://"
            value={v.website}
            onChange={(e) => setV({ ...v, website: e.target.value })}
          />
        </div>
      </FormModal>

      <FormModal
        open={contactOpen}
        onOpenChange={setContactOpen}
        title={contactId ? 'Edit contact' : 'Add contact'}
        pending={saveContact.isPending}
        error={contactError}
        onSubmit={() => {
          if (!contact.name.trim()) return setContactError('Enter a name.');
          setContactError('');
          saveContact.mutate();
        }}
      >
        {(
          [
            ['name', 'Name', 'text'],
            ['role', 'Role', 'text'],
            ['email', 'Email', 'email'],
            ['phone', 'Phone', 'tel'],
          ] as const
        ).map(([k, label, type]) => (
          <div key={k} className="space-y-1.5">
            <Label htmlFor={`ec-c-${k}`}>{label}</Label>
            <Input
              id={`ec-c-${k}`}
              type={type}
              value={contact[k]}
              onChange={(e) => setContact({ ...contact, [k]: e.target.value })}
            />
          </div>
        ))}
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={contact.is_primary}
            onCheckedChange={(x) =>
              setContact({ ...contact, is_primary: x === true })
            }
          />
          Primary contact
        </label>
      </FormModal>
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={removing ? `Remove ${removing.name}?` : ''}
        description="They are removed from your company's contacts. Their sign-in account, if any, is not affected."
        confirmLabel="Remove"
        onConfirm={() => removing && removeContact.mutate(removing.id)}
      />
    </div>
  );
}
