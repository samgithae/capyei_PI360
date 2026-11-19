import { useState } from 'react';
import { errorText, Required } from '@/pages/cases/case-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { toast } from 'sonner';
import { api, post } from '@/lib/api';
import { formatDate } from '@/lib/helpers';
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
import { DataCard } from '@/components/data-card';
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { ErrorState, LoadingState } from '@/components/states';

type Grant = {
  id: number;
  user: { id: number; username: string; name: string };
  permission: string;
  label: string;
  purpose: string;
  granted_by: string;
  granted_at: string;
  expires_at: string;
  revoked_at: string | null;
  state: 'active' | 'expired' | 'revoked';
};
type Overview = {
  grantable: { code: string; label: string }[];
  max_days: number;
  results: Grant[];
};
type StaffUser = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
};

const STATE = {
  active: { label: 'Active', variant: 'success' },
  expired: { label: 'Expired', variant: 'secondary' },
  revoked: { label: 'Withdrawn', variant: 'secondary' },
} as const;

const isoDay = (offset: number) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

function GrantDialog({
  data,
  onOpenChange,
}: {
  data: Overview;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const users = useQuery({
    queryKey: ['users', ''],
    queryFn: () => api<StaffUser[]>('/identity/users?q='),
  });
  const [user, setUser] = useState('');
  const [permission, setPermission] = useState(
    data.grantable.length === 1 ? data.grantable[0].code : '',
  );
  const [purpose, setPurpose] = useState('');
  const [expires, setExpires] = useState(isoDay(30));
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () =>
      post('/identity/grants', {
        user_id: Number(user),
        permission,
        purpose: purpose.trim(),
        expires_on: expires,
      }),
    onSuccess: () => {
      toast.success('Access granted.');
      void qc.invalidateQueries({ queryKey: ['grants'] });
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open
      onOpenChange={onOpenChange}
      title="Grant restricted access"
      description="A restricted permission is never part of a role. It is given to one person, for a stated purpose, until a date you choose."
      submitLabel="Grant access"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        if (!user) return setError('Choose the person.');
        if (!permission) return setError('Choose what they may do.');
        if (!purpose.trim()) return setError('Say why they need this.');
        if (expires > isoDay(data.max_days) || expires < isoDay(0))
          return setError(
            `Choose a date from today up to ${data.max_days} days ahead.`,
          );
        setError('');
        save.mutate();
      }}
    >
      <SelectField
        label="Person"
        value={user}
        emptyLabel="Choose a person"
        options={(users.data ?? [])
          .filter((u) => u.is_active)
          .map((u) => ({
            id: String(u.id),
            name: `${u.first_name} ${u.last_name}`.trim() || u.username,
          }))}
        onChange={setUser}
      />
      <SelectField
        label="Permission"
        value={permission}
        emptyLabel="Choose a permission"
        options={data.grantable.map((g) => ({ id: g.code, name: g.label }))}
        onChange={setPermission}
      />
      <div className="space-y-1.5">
        <Label htmlFor="grant-purpose">
          Purpose
          <Required />
        </Label>
        <Input
          id="grant-purpose"
          value={purpose}
          maxLength={300}
          onChange={(e) => setPurpose(e.target.value)}
          placeholder="e.g. Quarterly follow-up call lists for Mombasa"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="grant-expires">
          Access ends at the end of
          <Required />
        </Label>
        <Input
          id="grant-expires"
          type="date"
          value={expires}
          min={isoDay(0)}
          max={isoDay(data.max_days)}
          onChange={(e) => setExpires(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

function RevokeDialog({
  grant,
  onOpenChange,
}: {
  grant: Grant;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const revoke = useMutation({
    mutationFn: () =>
      post(`/identity/grants/${grant.id}/revoke`, { reason: reason.trim() }),
    onSuccess: () => {
      toast.success('Access withdrawn.');
      void qc.invalidateQueries({ queryKey: ['grants'] });
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open
      onOpenChange={onOpenChange}
      title="Withdraw access"
      description={`${grant.user.name || grant.user.username} will lose "${grant.label}" straight away.`}
      submitLabel="Withdraw"
      pending={revoke.isPending}
      error={error}
      onSubmit={() => {
        if (!reason.trim()) return setError('Say why it is withdrawn.');
        setError('');
        revoke.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="revoke-reason">
          Reason
          <Required />
        </Label>
        <Input
          id="revoke-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
    </FormModal>
  );
}

export function AccessGrantsPage() {
  const [granting, setGranting] = useState(false);
  const [revoking, setRevoking] = useState<Grant | null>(null);
  const q = useQuery({
    queryKey: ['grants'],
    queryFn: () => api<Overview>('/identity/grants'),
  });

  return (
    <>
      <Helmet>
        <title>Access grants</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Administration', to: '/administration' },
          { label: 'Access grants' },
        ]}
        title="Access grants"
        description="Restricted permissions, such as exporting lists with names, are given to one person for a stated purpose and a limited time."
        actions={
          <Button onClick={() => setGranting(true)}>Grant access</Button>
        }
      />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : (
        <DataCard title="Grants">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Person</TableHead>
                <TableHead>Permission</TableHead>
                <TableHead>Purpose</TableHead>
                <TableHead>Ends</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.results.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-muted-foreground">
                    No restricted access has been granted yet.
                  </TableCell>
                </TableRow>
              )}
              {q.data.results.map((g) => (
                <TableRow key={g.id}>
                  <TableCell>
                    {g.user.name || g.user.username}
                    <div className="text-xs text-muted-foreground">
                      Granted by {g.granted_by || 'system'}
                    </div>
                  </TableCell>
                  <TableCell>{g.label}</TableCell>
                  <TableCell className="max-w-xs">{g.purpose}</TableCell>
                  <TableCell>{formatDate(g.expires_at)}</TableCell>
                  <TableCell>
                    <Badge variant={STATE[g.state].variant}>
                      {STATE[g.state].label}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-end">
                    {g.state === 'active' && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setRevoking(g)}
                      >
                        Withdraw
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </DataCard>
      )}
      {granting && q.data && (
        <GrantDialog data={q.data} onOpenChange={() => setGranting(false)} />
      )}
      {revoking && (
        <RevokeDialog grant={revoking} onOpenChange={() => setRevoking(null)} />
      )}
    </>
  );
}
