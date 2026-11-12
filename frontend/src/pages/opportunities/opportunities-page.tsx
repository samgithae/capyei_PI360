import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DataCard,
  FilterSelect,
  Pager,
  SearchBox,
} from '@/components/data-card';
import {
  BulkBar,
  RowActions,
  RowCheckbox,
  SelectAllHead,
  ShowArchived,
  useArchiveFlow,
  useSelection,
} from '@/components/shared/bulk';
import { SummaryStatCard } from '@/components/shared/info-card';
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { EditOpportunity } from './opportunity-edit';

interface Row {
  id: string;
  title: string;
  employer: string;
  kind: string;
  status: string;
  county: string;
  positions: number;
  closing_date: string | null;
  archived: boolean;
}
interface Page {
  total: number;
  page_size: number;
  results: Row[];
}
interface EmployerPage {
  results: { id: string; name: string }[];
}

const KINDS = ['job', 'internship', 'apprenticeship', 'other'];
const STATUSES = ['draft', 'open', 'closed', 'expired'];

function AddOpportunity({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const nav = useNavigate();
  const [search, setSearch] = useState('');
  const [v, setV] = useState({
    employer_id: '',
    title: '',
    kind: 'job',
    positions: '1',
    closing_date: '',
  });
  const [error, setError] = useState('');
  const employers = useQuery({
    queryKey: ['employer-search', search],
    queryFn: () =>
      api<EmployerPage>(`/employers?q=${encodeURIComponent(search)}`),
    enabled: open,
  });
  const create = useMutation({
    mutationFn: () =>
      post<{ id: string }>('/opportunities', {
        ...v,
        positions: Number(v.positions),
        closing_date: v.closing_date || null,
      }),
    onSuccess: (o) => {
      toast.success('Opportunity saved as a draft.');
      nav(`/opportunities/${o.id}`);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });
  return (
    <FormModal
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setError('');
      }}
      title="Add opportunity"
      description="It is saved as a draft. Add requirements, then open it."
      submitLabel="Save as draft"
      pending={create.isPending}
      error={error}
      onSubmit={() => {
        if (!v.employer_id) return setError('Choose an employer.');
        setError('');
        create.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="opp-employer-search">
          Employer <span className="text-destructive">*</span>
        </Label>
        <Input
          id="opp-employer-search"
          placeholder="Search employers by name"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select
          value={v.employer_id}
          onValueChange={(x) => setV({ ...v, employer_id: x })}
        >
          <SelectTrigger aria-label="Employer">
            <SelectValue placeholder="Choose employer" />
          </SelectTrigger>
          <SelectContent>
            {employers.data?.results.map((e) => (
              <SelectItem key={e.id} value={e.id}>
                {e.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="opp-title">
          Title <span className="text-destructive">*</span>
        </Label>
        <Input
          id="opp-title"
          required
          value={v.title}
          onChange={(e) => setV({ ...v, title: e.target.value })}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label>Type</Label>
          <Select value={v.kind} onValueChange={(x) => setV({ ...v, kind: x })}>
            <SelectTrigger aria-label="Type" className="capitalize">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KINDS.map((k) => (
                <SelectItem key={k} value={k} className="capitalize">
                  {k}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="opp-positions">Positions</Label>
          <Input
            id="opp-positions"
            type="number"
            min={1}
            value={v.positions}
            onChange={(e) => setV({ ...v, positions: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="opp-closing">Closing date</Label>
          <Input
            id="opp-closing"
            type="date"
            value={v.closing_date}
            onChange={(e) => setV({ ...v, closing_date: e.target.value })}
          />
        </div>
      </div>
    </FormModal>
  );
}

function useCount(status?: string) {
  const qs = status ? `?status=${status}` : '';
  return useQuery({
    queryKey: ['opportunity-count', status ?? 'all'],
    queryFn: () => api<Page>(`/opportunities${qs}`),
    select: (d) => d.total,
  });
}

export function OpportunitiesPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const offset = Number(params.get('offset') ?? 0);
  const page = useQuery({
    queryKey: ['opportunities', params.toString()],
    queryFn: () => api<Page>(`/opportunities?${params.toString()}`),
  });
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const data = page.data;
  const showArchived = params.get('archived') === '1';
  const canEdit = can('employers.edit');
  const canArchive = can('records.archive');
  const selection = useSelection(
    data?.results.map((o) => o.id) ?? [],
    params.toString(),
  );
  const archive = useArchiveFlow({
    path: '/opportunities',
    noun: 'opportunity',
    nounPlural: 'opportunities',
    queryKeys: ['opportunities', 'opportunity-count'],
    onDone: selection.clear,
  });
  const total = useCount();
  const open = useCount('open');
  const draft = useCount('draft');
  const closed = useCount('closed');
  const expired = useCount('expired');
  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Opportunities | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Opportunities' }]}
        title="Opportunities"
        description={
          total.data !== undefined
            ? `${total.data} ${total.data === 1 ? 'opportunity' : 'opportunities'} across all employers.`
            : 'Jobs, internships and apprenticeships from partner employers.'
        }
        actions={
          can('employers.edit') && (
            <Button onClick={() => setAdding(true)}>
              <Plus /> Add opportunity
            </Button>
          )
        }
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <SummaryStatCard label="Total" value={total.data} />
        <SummaryStatCard label="Open" value={open.data} />
        <SummaryStatCard label="Draft" value={draft.data} />
        <SummaryStatCard
          label="Closed or expired"
          value={
            closed.data !== undefined && expired.data !== undefined
              ? closed.data + expired.data
              : undefined
          }
        />
      </div>
      <AddOpportunity open={adding} onOpenChange={setAdding} />
      {archive.dialog}
      {editing && (
        <EditOpportunity id={editing} onClose={() => setEditing(null)} />
      )}
      <DataCard
        footer={
          data && data.total > 0 ? (
            <Pager
              offset={offset}
              pageSize={data.page_size}
              onPageSize={(n) => {
                const next = new URLSearchParams(params);
                next.set('page_size', String(n));
                next.delete('offset');
                setParams(next);
              }}
              total={data.total}
              onMove={(to) => {
                const next = new URLSearchParams(params);
                next.set('offset', String(Math.max(to, 0)));
                setParams(next);
              }}
            />
          ) : undefined
        }
        toolbar={
          <>
            <SearchBox
              placeholder="Search by title"
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="Any status"
              value={params.get('status') ?? ''}
              options={STATUSES.map((x) => ({ id: x, name: x }))}
              onChange={(v) => set('status', v)}
              className="w-36 capitalize"
            />
            <FilterSelect
              label="Any type"
              value={params.get('kind') ?? ''}
              options={KINDS.map((x) => ({ id: x, name: x }))}
              onChange={(v) => set('kind', v)}
              className="w-36 capitalize"
            />
            {canArchive && (
              <ShowArchived
                checked={showArchived}
                onChange={(v) => set('archived', v ? '1' : '')}
              />
            )}
          </>
        }
      >
        {page.isError && (
          <div className="p-5">
            <ErrorState error={page.error} onRetry={() => page.refetch()} />
          </div>
        )}
        {page.isPending && (
          <div className="p-5">
            <LoadingState />
          </div>
        )}
        {data && data.results.length > 0 && (
          <BulkBar
            count={selection.selected.length}
            noun="opportunity(ies)"
            archived={showArchived}
            canArchive={canArchive}
            onArchive={() => archive.request(selection.selected, true)}
            onRestore={() => archive.request(selection.selected, false)}
            onClear={selection.clear}
          />
        )}
        {data && data.results.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                {canArchive && <SelectAllHead selection={selection} />}
                <TableHead>Title</TableHead>
                <TableHead>Employer</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Positions</TableHead>
                <TableHead>Closes</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((o) => (
                <TableRow
                  key={o.id}
                  data-state={
                    selection.isSelected(o.id) ? 'selected' : undefined
                  }
                >
                  {canArchive && (
                    <TableCell>
                      <RowCheckbox
                        selection={selection}
                        id={o.id}
                        label={`Select ${o.title}`}
                      />
                    </TableCell>
                  )}
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/opportunities/${o.id}`}
                    >
                      {o.title}
                    </Link>
                  </TableCell>
                  <TableCell>{o.employer}</TableCell>
                  <TableCell className="capitalize">{o.kind}</TableCell>
                  <TableCell>{o.positions}</TableCell>
                  <TableCell>{o.closing_date ?? ''}</TableCell>
                  <TableCell>
                    <StatusBadge status={o.status} />
                  </TableCell>
                  <TableCell>
                    <RowActions
                      label={o.title}
                      viewTo={`/opportunities/${o.id}`}
                      archived={o.archived}
                      onEdit={canEdit ? () => setEditing(o.id) : undefined}
                      onArchive={
                        canArchive
                          ? () => archive.request([o.id], true)
                          : undefined
                      }
                      onRestore={
                        canArchive
                          ? () => archive.request([o.id], false)
                          : undefined
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {data && data.results.length === 0 && (
          <div className="p-5">
            <EmptyState
              title="No opportunities match"
              hint="Try changing or clearing the filters."
            />
          </div>
        )}
      </DataCard>
    </div>
  );
}
