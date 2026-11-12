import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Section } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';
import { ErrorState, LoadingState } from '@/components/states';

interface Row {
  key: string;
  group: 'A' | 'C';
  label: string;
  unit: string;
  help: string;
  default: number;
  minimum: number;
  value: number;
}

const GROUPS = {
  A: {
    title: 'Support priority flags',
    description:
      'When a youth is flagged for extra support. Each number can be changed at any time.',
  },
  C: {
    title: 'Employer evidence',
    description:
      'How much referral history an employer needs before a result is shown.',
  },
};

/** The numbers behind support flags and employer evidence, changed here without a release. */
export function RuleSettingsPage() {
  const { can } = useAuth();
  const canEdit = can('intelligence.manage_rules');
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const q = useQuery({
    queryKey: ['rule-settings'],
    queryFn: () => api<Row[]>('/rules/settings'),
  });
  const save = useMutation({
    mutationFn: (values: Record<string, number>) =>
      api<Row[]>('/rules/settings', {
        method: 'PUT',
        body: JSON.stringify({ values }),
      }),
    onSuccess: () => {
      toast.success('Settings saved.');
      setDraft({});
      setError('');
      void qc.invalidateQueries({ queryKey: ['rule-settings'] });
      void qc.invalidateQueries({ queryKey: ['employer-evidence'] });
      void qc.invalidateQueries({ queryKey: ['support-queue'] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <LoadingState />;

  const changed = Object.fromEntries(
    q.data
      .filter(
        (r) => draft[r.key] !== undefined && Number(draft[r.key]) !== r.value,
      )
      .map((r) => [r.key, Number(draft[r.key])]),
  );
  const dirty = Object.keys(changed).length > 0;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Rule settings | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Rules', to: '/rules' }, { label: 'Settings' }]}
        title="Rule settings"
        description="Starting values are filled in so the system works from day one. Change a number when CAP-YEI decides it; every change is recorded in the audit trail."
      />
      {(['A', 'C'] as const).map((g) => (
        <Section
          key={g}
          title={GROUPS[g].title}
          description={GROUPS[g].description}
        >
          <div className="space-y-4">
            {q.data
              .filter((r) => r.group === g)
              .map((r) => (
                <div key={r.key} className="space-y-1">
                  <Label htmlFor={r.key}>{r.label}</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id={r.key}
                      type="number"
                      min={r.minimum}
                      className="w-28"
                      disabled={!canEdit}
                      value={draft[r.key] ?? String(r.value)}
                      onChange={(e) =>
                        setDraft({ ...draft, [r.key]: e.target.value })
                      }
                    />
                    <span className="text-sm text-muted-foreground">
                      {r.unit} (starting value {r.default})
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{r.help}</p>
                </div>
              ))}
          </div>
        </Section>
      ))}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {canEdit && (
        <div className="flex gap-2">
          <Button
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate(changed as Record<string, number>)}
          >
            {save.isPending ? 'Saving...' : 'Save settings'}
          </Button>
          {dirty && (
            <Button variant="ghost" onClick={() => setDraft({})}>
              Discard changes
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
