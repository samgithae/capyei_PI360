import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate } from 'react-router';
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
import { Textarea } from '@/components/ui/textarea';
import {
  DataCard,
  FilterSelect,
  SearchBox,
  useClientPage,
} from '@/components/data-card';
import { RowActions } from '@/components/shared/bulk';
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { MODULES, useRefreshRules, type RuleSet } from './rules-shared';

const BLANK = { module: '', code: '', name: '', purpose: '' };

/** Rule sets (T-047): one per thing the system works out, each with numbered versions. */
export function RulesPage() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const refresh = useRefreshRules();
  const [q, setQ] = useState('');
  const [module, setModule] = useState('');
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(BLANK);
  const [error, setError] = useState('');

  const list = useQuery({
    queryKey: ['rules'],
    queryFn: () => api<RuleSet[]>('/rules'),
  });
  const create = useMutation({
    mutationFn: () => post<RuleSet>('/rules', form),
    onSuccess: (made) => {
      toast.success('Rule set created with version 1 as a draft.');
      setAdding(false);
      setForm(BLANK);
      refresh();
      navigate(`/rules/${made.id}`);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Something went wrong.'),
  });

  // The list is short (a few rule sets), so search and filter run in the browser.
  const needle = q.trim().toLowerCase();
  const rows = (list.data ?? []).filter(
    (r) =>
      (!module || r.module === module) &&
      (!needle || `${r.name} ${r.code}`.toLowerCase().includes(needle)),
  );

  const paged = useClientPage(rows);

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Rules | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Rules' }]}
        title="Rules"
        description="The rules behind support priority, compatibility and employer reliability. Each change is a new version; only one version is in force at a time."
        actions={
          can('intelligence.manage_rules') && (
            <Button
              onClick={() => {
                setError('');
                setAdding(true);
              }}
            >
              <Plus /> New rule set
            </Button>
          )
        }
      />
      <DataCard
        footer={paged.pager}
        toolbar={
          <>
            <SearchBox
              placeholder="Search by name or code"
              defaultValue={q}
              onSubmit={setQ}
            />
            <FilterSelect
              label="Any module"
              value={module}
              options={MODULES}
              onChange={setModule}
              className="w-72"
            />
          </>
        }
      >
        {list.isError && (
          <div className="p-5">
            <ErrorState error={list.error} onRetry={() => list.refetch()} />
          </div>
        )}
        {list.isPending && (
          <div className="p-5">
            <LoadingState />
          </div>
        )}
        {list.data && rows.length === 0 && (
          <div className="p-5">
            <EmptyState
              title={
                list.data.length ? 'No rule sets match' : 'No rule sets yet'
              }
              hint={
                list.data.length
                  ? 'Try another module or search.'
                  : 'A rule set starts with version 1 as a draft.'
              }
            />
          </div>
        )}
        {rows.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Rule set</TableHead>
                <TableHead>Module</TableHead>
                <TableHead>In force</TableHead>
                <TableHead>Latest version</TableHead>
                <TableHead>Awaiting decision</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {paged.rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/rules/${r.id}`}
                    >
                      {r.name}
                    </Link>
                    <p className="text-xs text-muted-foreground">{r.code}</p>
                  </TableCell>
                  <TableCell>{r.module_label}</TableCell>
                  <TableCell>
                    {r.active ? (
                      `Version ${r.active.number}`
                    ) : (
                      <span className="text-muted-foreground">
                        Nothing in force
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    {r.latest && (
                      <span className="flex items-center gap-2">
                        Version {r.latest.number}
                        <StatusBadge
                          status={r.latest.status}
                          label={r.latest.status_label}
                        />
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    {r.latest?.waiting
                      ? `${r.latest.waiting} parameter${r.latest.waiting === 1 ? '' : 's'}`
                      : 'None'}
                  </TableCell>
                  <TableCell>
                    <RowActions label={r.name} viewTo={`/rules/${r.id}`} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DataCard>

      <FormModal
        open={adding}
        onOpenChange={setAdding}
        title="New rule set"
        description="Creates the rule set with version 1 as an empty draft. Nothing takes effect until a version is approved and activated."
        submitLabel="Create"
        pending={create.isPending}
        error={error}
        onSubmit={() => {
          if (!form.module) return setError('Choose a module.');
          if (!/^[a-z0-9-]+$/.test(form.code))
            return setError(
              'The code uses lower-case letters, numbers and hyphens.',
            );
          if (!form.name.trim()) return setError('Give the rule set a name.');
          create.mutate();
        }}
      >
        <div className="space-y-1.5">
          <Label>
            Module <span className="text-destructive">*</span>
          </Label>
          <SelectField
            label="Choose a module"
            value={form.module}
            options={MODULES}
            onChange={(v) => setForm({ ...form, module: v })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rule-set-code">
            Code <span className="text-destructive">*</span>
          </Label>
          <Input
            id="rule-set-code"
            maxLength={60}
            placeholder="for example: support-priority"
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rule-set-name">
            Name <span className="text-destructive">*</span>
          </Label>
          <Input
            id="rule-set-name"
            maxLength={120}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rule-set-purpose">Purpose</Label>
          <Textarea
            id="rule-set-purpose"
            maxLength={2000}
            value={form.purpose}
            onChange={(e) => setForm({ ...form, purpose: e.target.value })}
          />
        </div>
      </FormModal>
    </div>
  );
}
