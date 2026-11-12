import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { ErrorState, LoadingState } from '@/components/states';

interface Sector {
  id: string;
  code: string;
  name: string;
  active: boolean;
}

/** A stable code made from the name, e.g. "Hospitality & Tourism" -> "hospitality-tourism". */
const codeFor = (name: string) =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);

export function SectorsPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const canManage = can('reference.manage');
  const [editing, setEditing] = useState<Sector | 'new' | null>(null);
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  const sectors = useQuery({
    queryKey: ['sectors-admin'],
    queryFn: () => api<Sector[]>('/config/reference/sectors'),
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['sectors-admin'] });
    void qc.invalidateQueries({ queryKey: ['employer-filters'] });
  };
  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'Could not save.');

  const save = useMutation({
    mutationFn: () =>
      editing === 'new'
        ? post('/config/reference/sectors', {
            name: name.trim(),
            code: codeFor(name),
          })
        : api(`/config/reference/sectors/${(editing as Sector).id}`, {
            method: 'PATCH',
            body: JSON.stringify({ name: name.trim() }),
          }),
    onSuccess: () => {
      toast.success(editing === 'new' ? 'Sector added' : 'Sector renamed');
      setEditing(null);
      refresh();
    },
    onError: fail,
  });

  const toggle = useMutation({
    mutationFn: (s: Sector) =>
      post(
        `/config/reference/sectors/${s.id}/${s.active ? 'deactivate' : 'reactivate'}`,
        { reason: '' },
      ),
    onSuccess: refresh,
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : 'Could not update.'),
  });

  const open = (s: Sector | 'new') => {
    setEditing(s);
    setName(s === 'new' ? '' : s.name);
    setError('');
  };

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Sectors | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Administration' }, { label: 'Sectors' }]}
        title="Sectors"
        description="The industries employers and opportunities are grouped under. Retiring a sector hides it from new records; existing records keep it."
        actions={
          canManage && <Button onClick={() => open('new')}>Add sector</Button>
        }
      />
      <DataCard title="All sectors">
        {sectors.isLoading ? (
          <LoadingState />
        ) : sectors.isError ? (
          <ErrorState
            error={sectors.error}
            onRetry={() => void sectors.refetch()}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Name</TableHead>
                <TableHead>Code</TableHead>
                <TableHead>Status</TableHead>
                {canManage && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {sectors.data?.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {s.code}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={s.active ? 'success' : 'secondary'}
                      appearance="light"
                    >
                      {s.active ? 'Active' : 'Retired'}
                    </Badge>
                  </TableCell>
                  {canManage && (
                    <TableCell className="space-x-2 text-end">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => open(s)}
                      >
                        Rename
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => toggle.mutate(s)}
                      >
                        {s.active ? 'Retire' : 'Reactivate'}
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DataCard>

      <FormModal
        open={editing !== null}
        onOpenChange={(o) => !o && setEditing(null)}
        title={editing === 'new' ? 'Add sector' : 'Rename sector'}
        submitLabel={editing === 'new' ? 'Add' : 'Save'}
        pending={save.isPending}
        error={error}
        onSubmit={() => save.mutate()}
      >
        <Input
          aria-label="Sector name"
          placeholder="Sector name, e.g. Renewable energy"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
        />
      </FormModal>
    </div>
  );
}
