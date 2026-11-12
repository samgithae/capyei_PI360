import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Copy, Pencil, Trash2 } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link, useNavigate, useParams } from 'react-router';
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
import { Textarea } from '@/components/ui/textarea';
import {
  ActivityTimeline,
  type AuditEvent,
} from '@/components/shared/activity-timeline';
import { DetailList, Section } from '@/components/shared/info-card';
import { ConfirmDialog, FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { StatusBadge } from '@/components/shared/status-badge';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
} from '@/components/states';
import { RuleEditor } from './rule-editor';
import {
  expected,
  parseValue,
  show,
  useRefreshRules,
  weightText,
  when,
  type Definition,
  type Operator,
  type StepName,
  type VersionDetail,
} from './rules-shared';

// One entry per lifecycle step: the button, the dialog text, and whether a note is asked for.
const STEPS: Record<
  StepName,
  {
    button: string;
    title: string;
    description: string;
    note?: { label: string; required?: boolean };
    done: string;
    primary?: boolean;
  }
> = {
  submit: {
    button: 'Send for review',
    title: 'Send this draft for review',
    description:
      'The draft is checked and then locked. A reviewer can approve it or return it to you.',
    done: 'Sent for review.',
    primary: true,
  },
  return: {
    button: 'Return to draft',
    title: 'Return this version to draft',
    description: 'Say what needs to change so the author can fix it.',
    note: { label: 'What needs to change', required: true },
    done: 'Returned to draft.',
  },
  approve: {
    button: 'Approve',
    title: 'Approve this version',
    description:
      'Approval records that the rules were reviewed. It does not put them in force; activation does.',
    note: { label: 'Note' },
    done: 'Version approved.',
    primary: true,
  },
  activate: {
    button: 'Activate',
    title: 'Put this version in force',
    description:
      'From now on results are worked out with this version. The version in force today is retired. Your name, the time and this note are recorded.',
    note: { label: 'Note' },
    done: 'Version activated. It is now in force.',
    primary: true,
  },
  deactivate: {
    button: 'Deactivate',
    title: 'Take this version out of force',
    description:
      'Use this only when the rules are wrong. The version it replaced comes back into force, if there is one.',
    note: { label: 'Reason', required: true },
    done: 'Version deactivated.',
  },
  clone: {
    button: 'Copy as new draft',
    title: 'Copy as a new draft',
    description:
      'Makes the next version number as a draft with the same rules, ready to edit.',
    note: { label: 'What will change' },
    done: 'New draft created.',
  },
};
const STEP_ORDER: StepName[] = [
  'submit',
  'approve',
  'activate',
  'return',
  'deactivate',
  'clone',
];

const patch = <T,>(path: string, body: unknown) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(body) });

/** One rule version (T-047): its factors and parameters, where it is in the lifecycle, and
 * the audit trail of who drafted, approved and activated it. */
export function RuleVersionPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const refresh = useRefreshRules();
  const [step, setStep] = useState<StepName | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<'wizard' | 'json' | null>(null);
  const [draft, setDraft] = useState({ json: '', notes: '' });
  const [param, setParam] = useState<string | null>(null);
  const [paramForm, setParamForm] = useState({ value: '', approved: false });
  const [discarding, setDiscarding] = useState(false);

  const q = useQuery({
    queryKey: ['rule-version', id],
    queryFn: () => api<VersionDetail>(`/rules/versions/${id}`),
    retry: false,
  });
  const audit = useQuery({
    queryKey: ['rule-version-history', id],
    queryFn: () => api<AuditEvent[]>(`/rules/versions/${id}/history`),
  });
  const operators = useQuery({
    queryKey: ['rule-operators'],
    queryFn: () => api<Operator[]>('/rules/operators'),
    staleTime: Infinity, // the operator set only changes with a release
  });

  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'Something went wrong.');
  const close = () => {
    setStep(null);
    setEditing(null);
    setParam(null);
    setNote('');
    setError('');
  };

  const run = useMutation({
    mutationFn: () =>
      post<VersionDetail>(`/rules/versions/${id}/${step}`, { note }),
    onSuccess: (result) => {
      if (step) toast.success(STEPS[step].done);
      const made = step === 'clone' ? result.id : null;
      close();
      refresh();
      if (made) navigate(`/rules/versions/${made}`);
    },
    onError: fail,
  });
  const save = useMutation({
    mutationFn: (body: { definition?: Definition; change_notes?: string }) =>
      patch<VersionDetail>(`/rules/versions/${id}`, body),
    onSuccess: () => {
      toast.success('Draft saved.');
      close();
      refresh();
    },
    onError: fail,
  });
  const discard = useMutation({
    mutationFn: () => api(`/rules/versions/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Draft discarded.');
      refresh();
      navigate(`/rules/${q.data?.rule_set.id ?? ''}`);
    },
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : 'Something went wrong.'),
  });

  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Rule version not found"
            hint="It may have been discarded, or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        <Link className="text-primary" to="/rules">
          Back to rules
        </Link>
      </div>
    );
  }
  const v = q.data;
  if (!v) return <LoadingState />;

  const d = v.definition ?? {};
  const factors = d.factors ?? [];
  const parameters = Object.entries(d.parameters ?? {});
  const canEdit = v.actions.includes('edit');
  const opLabel = (code: string) =>
    operators.data?.find((o) => o.code === code)?.label ?? code;
  const current = step ? STEPS[step] : null;

  const openEdit = () => {
    setDraft({ json: JSON.stringify(d, null, 2), notes: v.change_notes });
    setError('');
    setEditing('wizard');
  };
  const openParam = (name: string) => {
    const p = d.parameters?.[name];
    setParamForm({
      value:
        p?.value === null || p?.value === undefined
          ? ''
          : typeof p.value === 'string'
            ? p.value
            : JSON.stringify(p.value),
      approved: p?.approved === true,
    });
    setError('');
    setParam(name);
  };

  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{`${v.rule_set.name}, version ${v.number} | PI 360`}</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Rules', to: '/rules' },
          { label: v.rule_set.name, to: `/rules/${v.rule_set.id}` },
          { label: `Version ${v.number}` },
        ]}
        title={`${v.rule_set.name}, version ${v.number}`}
        badges={<StatusBadge status={v.status} label={v.status_label} />}
        meta={
          <>
            <span>{v.rule_set.module_label}</span>
            {v.cloned_from && <span>Copied from version {v.cloned_from}</span>}
          </>
        }
        actions={
          <>
            {canEdit && (
              <Button variant="outline" onClick={openEdit}>
                <Pencil /> Edit draft
              </Button>
            )}
            {STEP_ORDER.filter((s) => v.actions.includes(s)).map((s) => (
              <Button
                key={s}
                variant={STEPS[s].primary ? 'primary' : 'outline'}
                onClick={() => {
                  setNote('');
                  setError('');
                  setStep(s);
                }}
              >
                {s === 'clone' && <Copy />}
                {STEPS[s].button}
              </Button>
            ))}
            {v.actions.includes('discard') && (
              <Button variant="outline" onClick={() => setDiscarding(true)}>
                <Trash2 /> Discard
              </Button>
            )}
          </>
        }
      />

      {v.status === 'active' && (
        <Notice
          tone="info"
          title="This version is in force and cannot be edited."
        >
          To change the rules, copy it as a new draft, edit the copy and send it
          for review.
        </Notice>
      )}
      {v.status === 'retired' && (
        <Notice tone="info" title="This version is retired.">
          It is kept so that earlier results can still be explained.
        </Notice>
      )}
      {v.problems.length > 0 && (
        <Notice
          tone="warning"
          title="This draft cannot be sent for review yet."
        >
          <ul className="list-disc ps-5">
            {v.problems.map((p) => (
              <li key={p.path + p.message}>
                {p.path ? `${p.path}: ` : ''}
                {p.message}
              </li>
            ))}
          </ul>
        </Notice>
      )}
      {v.unapproved.length > 0 && (
        <Notice
          tone="warning"
          title={`${v.unapproved.length} parameter${v.unapproved.length === 1 ? ' is' : 's are'} waiting for a decision.`}
        >
          This version cannot be approved until each has a value and is marked
          as decided: {v.unapproved.join(', ')}.
        </Notice>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Section
            title="Factors"
            description="Each factor is one check. A missing value gives unknown, never a silent fail."
            flush
          >
            {factors.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No factors yet"
                  hint={
                    canEdit
                      ? 'Use Edit draft to add the first factor.'
                      : undefined
                  }
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead>Factor</TableHead>
                      <TableHead>Check</TableHead>
                      <TableHead>Kind</TableHead>
                      <TableHead>If unknown</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {factors.map((f) => (
                      <TableRow key={f.code}>
                        <TableCell className="whitespace-normal">
                          <p className="font-medium text-foreground">
                            {f.label}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {f.code}
                            {f.enabled === false && ' · switched off'}
                          </p>
                          {f.note && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              {f.note}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="whitespace-normal">
                          <p>
                            <span className="text-muted-foreground">
                              {f.field}
                            </span>{' '}
                            {opLabel(f.operator)}: {expected(f, d)}
                          </p>
                          {f.max_age_days && (
                            <p className="text-xs text-muted-foreground">
                              Ignored if older than {f.max_age_days} days
                            </p>
                          )}
                        </TableCell>
                        <TableCell>
                          {f.mandatory ? (
                            <Badge variant="warning" appearance="light">
                              Mandatory
                            </Badge>
                          ) : f.mandatory_from_requirement ? (
                            <>
                              Set by the opportunity
                              <p className="text-xs text-muted-foreground">
                                Weight when preferred: {weightText(f, d)}
                              </p>
                            </>
                          ) : (
                            `Preferred, weight ${weightText(f, d)}`
                          )}
                        </TableCell>
                        <TableCell>
                          {f.unknown_policy === 'exclude'
                            ? 'Leave out'
                            : 'Show as a gap'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </Section>

          <Section
            title="Parameters"
            description="Thresholds and weights the factors use. Each needs a decision from the product owner before the version can be approved."
            flush
          >
            {parameters.length === 0 ? (
              <div className="p-5">
                <EmptyState title="This version has no parameters" />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead>Parameter</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Decision</TableHead>
                      <TableHead>Status</TableHead>
                      {canEdit && (
                        <TableHead className="w-28">
                          <span className="sr-only">Actions</span>
                        </TableHead>
                      )}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {parameters.map(([name, p]) => {
                      const decided =
                        p.approved === true &&
                        p.value !== null &&
                        p.value !== undefined;
                      return (
                        <TableRow key={name}>
                          <TableCell className="whitespace-normal">
                            <p className="font-medium text-foreground">
                              {p.label || name}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {name}
                            </p>
                            {p.note && (
                              <p className="text-xs text-muted-foreground">
                                {p.note}
                              </p>
                            )}
                          </TableCell>
                          <TableCell>
                            {p.value === null || p.value === undefined ? (
                              <span className="text-muted-foreground">
                                Not set
                              </span>
                            ) : (
                              `${show(p.value)}${p.unit ? ` ${p.unit}` : ''}`
                            )}
                          </TableCell>
                          <TableCell>{p.decision || '-'}</TableCell>
                          <TableCell>
                            <Badge
                              variant={decided ? 'success' : 'warning'}
                              appearance="light"
                            >
                              {decided ? 'Decided' : 'Awaiting decision'}
                            </Badge>
                          </TableCell>
                          {canEdit && (
                            <TableCell>
                              <Button
                                size="sm"
                                variant="outline"
                                aria-label={`Set value for ${p.label || name}`}
                                onClick={() => openParam(name)}
                              >
                                Set value
                              </Button>
                            </TableCell>
                          )}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </Section>

          {d.notes && (
            <Section title="Notes">
              <p className="whitespace-pre-line text-sm text-foreground">
                {d.notes}
              </p>
            </Section>
          )}
        </div>

        <div className="space-y-5">
          <Section title="Details">
            <DetailList
              items={[
                {
                  label: 'Status',
                  value: (
                    <StatusBadge status={v.status} label={v.status_label} />
                  ),
                },
                { label: 'What changed', value: v.change_notes },
                { label: 'Created by', value: v.created_by || 'System' },
                { label: 'Created', value: when(v.created_at) },
                { label: 'Sent for review by', value: v.submitted_by },
                { label: 'Approved by', value: v.approved_by },
                { label: 'Approved', value: when(v.approved_at) },
                { label: 'Activated by', value: v.activated_by },
                { label: 'In force from', value: when(v.effective_from) },
                { label: 'Retired', value: when(v.retired_at) },
                {
                  label: 'Fingerprint',
                  value: (
                    <span className="font-mono text-xs">
                      {v.definition_hash.slice(0, 12)}
                    </span>
                  ),
                },
              ]}
            />
          </Section>
          <Section
            title="Activity"
            description="Every step is recorded with who did it and when."
          >
            {audit.isPending ? (
              <LoadingState rows={3} />
            ) : (
              <ActivityTimeline events={audit.data ?? []} />
            )}
          </Section>
        </div>
      </div>

      <FormModal
        open={step !== null}
        onOpenChange={(o) => !o && close()}
        title={current?.title ?? ''}
        description={current?.description}
        submitLabel={current?.button}
        pending={run.isPending}
        error={error}
        onSubmit={() => {
          if (current?.note?.required && !note.trim())
            return setError(`${current.note.label} is needed.`);
          run.mutate();
        }}
      >
        {current?.note && (
          <div className="space-y-1.5">
            <Label htmlFor="rule-step-note">
              {current.note.label}
              {current.note.required && (
                <span className="text-destructive"> *</span>
              )}
            </Label>
            <Textarea
              id="rule-step-note"
              maxLength={2000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        )}
      </FormModal>

      {editing === 'wizard' && (
        <RuleEditor
          definition={d}
          notes={v.change_notes}
          pending={save.isPending}
          error={error}
          onClose={close}
          onSave={(definition, change_notes) =>
            save.mutate({ definition, change_notes })
          }
          onAdvanced={() => setEditing('json')}
        />
      )}

      <FormModal
        open={editing === 'json'}
        onOpenChange={(o) => !o && close()}
        title="Edit draft (JSON)"
        description="The rules as JSON: factors, parameters and notes. Saving checks the shape and lists anything to fix."
        pending={save.isPending}
        error={error}
        onSubmit={() => {
          let definition: Definition;
          try {
            definition = JSON.parse(draft.json);
          } catch {
            return setError(
              'This is not valid JSON. Check the commas and quotes.',
            );
          }
          save.mutate({ definition, change_notes: draft.notes });
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="rule-change-notes">What changed</Label>
          <Input
            id="rule-change-notes"
            maxLength={4000}
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rule-definition">Definition</Label>
          <Textarea
            id="rule-definition"
            className="h-80 font-mono text-xs"
            spellCheck={false}
            value={draft.json}
            onChange={(e) => setDraft({ ...draft, json: e.target.value })}
          />
        </div>
      </FormModal>

      <FormModal
        open={param !== null}
        onOpenChange={(o) => !o && close()}
        title={`Set ${param ? d.parameters?.[param]?.label || param : 'value'}`}
        description="Record the value that was decided. Tick the box only when the product owner has confirmed it."
        pending={save.isPending}
        error={error}
        onSubmit={() => {
          if (!param) return;
          const value = parseValue(paramForm.value);
          if (paramForm.approved && value === null)
            return setError('A decided parameter needs a value.');
          save.mutate({
            definition: {
              ...d,
              parameters: {
                ...d.parameters,
                [param]: {
                  ...d.parameters?.[param],
                  value,
                  approved: paramForm.approved,
                },
              },
            },
          });
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="rule-param-value">
            Value
            {param && d.parameters?.[param]?.unit
              ? ` (${d.parameters[param].unit})`
              : ''}
          </Label>
          <Input
            id="rule-param-value"
            value={paramForm.value}
            onChange={(e) =>
              setParamForm({ ...paramForm, value: e.target.value })
            }
          />
          <p className="text-xs text-muted-foreground">
            A number such as 90, or a list such as [1, 2]. Leave empty while it
            is undecided.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={paramForm.approved}
            onCheckedChange={(c) =>
              setParamForm({ ...paramForm, approved: c === true })
            }
          />
          Decided
          {param && d.parameters?.[param]?.decision
            ? ` (decision ${d.parameters[param].decision})`
            : ''}
        </label>
      </FormModal>

      <ConfirmDialog
        open={discarding}
        onOpenChange={setDiscarding}
        title="Discard this draft?"
        description={`Version ${v.number} is removed. This cannot be undone. The discard itself stays in the audit trail.`}
        confirmLabel="Discard"
        onConfirm={() => discard.mutate()}
      />
    </div>
  );
}
