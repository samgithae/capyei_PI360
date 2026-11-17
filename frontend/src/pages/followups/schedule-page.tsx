import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { errorText, Required } from '@/pages/cases/case-shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { toast } from 'sonner';
import { api, post } from '@/lib/api';
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
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { ErrorState, LoadingState } from '@/components/states';
import { KIND_OPTIONS, type ScheduleStep } from './followup-shared';

const MAX_DAYS = 732;

/** "30 days", "6 months" and so on, for reading a day count at a glance. */
function roughly(days: number) {
  if (days < 60) return `${days} days`;
  const months = Math.round(days / 30.4);
  return `about ${months} months`;
}

function StepDialog({
  step,
  onOpenChange,
}: {
  step: ScheduleStep | 'new';
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const editing = step !== 'new' ? step : null;
  const [kind, setKind] = useState(editing?.kind ?? 'early');
  const [label, setLabel] = useState(editing?.label ?? '');
  const [days, setDays] = useState(String(editing?.offset_days ?? ''));
  const [active, setActive] = useState(editing ? editing.active : true);
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () => {
      const body = {
        kind,
        label: label.trim(),
        offset_days: Number(days),
        active,
      };
      return editing
        ? api(`/followups/steps/${editing.id}`, {
            method: 'PATCH',
            body: JSON.stringify(body),
          })
        : post('/followups/steps', body);
    },
    onSuccess: () => {
      toast.success('Schedule saved. It applies to new placements only.');
      void qc.invalidateQueries({ queryKey: ['followup-steps'] });
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });
  return (
    <FormModal
      open
      onOpenChange={onOpenChange}
      title={editing ? 'Edit follow-up step' : 'Add a follow-up step'}
      description="Placements already confirmed keep the check-ins they have. Only placements recorded from now on use this change."
      submitLabel="Save step"
      pending={save.isPending}
      error={error}
      onSubmit={() => {
        const n = Number(days);
        if (!label.trim()) return setError('Give the step a name.');
        if (!Number.isInteger(n) || n < 1 || n > MAX_DAYS)
          return setError(
            `Give a whole number of days from 1 to ${MAX_DAYS} (24 months).`,
          );
        setError('');
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label>
          Kind
          <Required />
        </Label>
        <SelectField
          label="Choose kind"
          value={kind}
          options={KIND_OPTIONS}
          onChange={(v) => setKind(v as 'early' | 'tracer')}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="step-label">
          Name
          <Required />
        </Label>
        <Input
          id="step-label"
          maxLength={60}
          placeholder="e.g. 6 months"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="step-days">
          Days after the placement starts
          <Required />
        </Label>
        <Input
          id="step-days"
          type="number"
          min={1}
          max={MAX_DAYS}
          value={days}
          onChange={(e) => setDays(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label>Use for new placements</Label>
        <SelectField
          label="Active or paused"
          value={active ? 'yes' : 'no'}
          options={[
            { id: 'yes', name: 'Yes, active' },
            { id: 'no', name: 'No, paused' },
          ]}
          onChange={(v) => setActive(v === 'yes')}
        />
      </div>
    </FormModal>
  );
}

/** The follow-up schedule: how many days after a placement starts each check-in falls due.
 * Changing it never rewrites check-ins that already exist (FR-25). */
export function FollowUpSchedulePage() {
  const { can } = useAuth();
  const canManage = can('config.manage');
  const [editing, setEditing] = useState<ScheduleStep | 'new' | null>(null);
  const q = useQuery({
    queryKey: ['followup-steps'],
    queryFn: () => api<{ results: ScheduleStep[] }>('/followups/steps'),
  });
  const steps = q.data?.results ?? [];

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Follow-up schedule | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Administration', to: '/administration' },
          { label: 'Follow-up schedule' },
        ]}
        title="Follow-up schedule"
        description="When each check-in falls due, counted from the day a placement starts. A change affects placements recorded after it; check-ins already made keep their dates."
        actions={
          canManage ? (
            <Button onClick={() => setEditing('new')}>Add step</Button>
          ) : undefined
        }
      />
      {q.isError && (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      )}
      {q.isPending && <LoadingState />}
      {q.data && (
        <Section title="Steps" flush>
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Name</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Falls due</TableHead>
                <TableHead>State</TableHead>
                {canManage && <TableHead className="w-24" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {steps.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.label}</TableCell>
                  <TableCell>{s.kind_label}</TableCell>
                  <TableCell>
                    {s.offset_days} days
                    <p className="text-xs text-muted-foreground">
                      {roughly(s.offset_days)} after the start
                    </p>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={s.active ? 'success' : 'secondary'}
                      appearance="light"
                    >
                      {s.active ? 'Active' : 'Paused'}
                    </Badge>
                  </TableCell>
                  {canManage && (
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditing(s)}
                      >
                        Edit
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}
      {editing && (
        <StepDialog
          key={editing === 'new' ? 'new' : editing.id}
          step={editing}
          onOpenChange={(o) => !o && setEditing(null)}
        />
      )}
    </div>
  );
}
