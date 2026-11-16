import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { DetailList, Section } from '@/components/shared/info-card';
import { FormModal } from '@/components/shared/modals';
import { MultiSelectField } from '@/components/shared/multi-select-field';
import { PageHeader } from '@/components/shared/page-header';
import { ErrorState, LoadingState } from '@/components/states';
import { CompanyLogo } from './company-logo';
import type { Ref } from './employer-types';

const DESCRIPTION_MAX = 600;

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
  description: string;
  logo_version: string | null;
  options: { sectors: Ref[]; counties: Ref[] };
}

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
    description: '',
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
        description: p.description,
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
      <Section
        title="Logo and about"
        description="Shown to PI 360 staff. Keep the description short: who you are and what you do."
      >
        <div className="space-y-5">
          <CompanyLogo
            version={p.logo_version}
            canEdit={canEdit}
            onChanged={refresh}
          />
          {p.description ? (
            <p className="whitespace-pre-line text-sm">{p.description}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              No description yet.
              {canEdit && ' Use Edit details to add one.'}
            </p>
          )}
        </div>
      </Section>
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
      <Section title="People">
        <p className="text-sm text-muted-foreground">
          The people PI 360 can reach, and who can sign in to this portal, are
          on one list.{' '}
          <Link className="text-primary underline" to="/employer/people">
            Open People
          </Link>
        </p>
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
          <Label htmlFor="ec-about">About the company</Label>
          <Textarea
            id="ec-about"
            rows={4}
            maxLength={DESCRIPTION_MAX}
            placeholder="Who you are and what you do, in a few sentences."
            value={v.description}
            onChange={(e) => setV({ ...v, description: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">
            {v.description.length} / {DESCRIPTION_MAX}
          </p>
        </div>
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
    </div>
  );
}
