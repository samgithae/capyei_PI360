import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { toast } from 'sonner';
import { api, ApiError } from '@/lib/api';
import { Switch } from '@/components/ui/switch';
import { Section } from '@/components/shared/info-card';
import { ConfirmDialog } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { ErrorState, LoadingState } from '@/components/states';

interface Flag {
  key: string;
  description: string;
  enabled: boolean;
}

/** The two switches that shape the employer portal. Both start off. */
const PORTAL: Record<string, { title: string; on: string; off: string }> = {
  employer_self_publish: {
    title: 'Employers publish their own opportunities',
    on: 'On: an employer opens an opportunity straight away. Staff are not asked.',
    off: 'Off: every opportunity an employer submits waits for PI staff to approve it.',
  },
  employer_mfa_required: {
    title: 'Require a second sign-in step for employer users',
    on: 'On: employer users must use an authenticator app to sign in.',
    off: 'Off: employer users sign in with a password only, like youth.',
  },
};

export function PortalSettingsPage() {
  const { can } = useAuth();
  const canManage = can('config.manage');
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['flags'],
    queryFn: () => api<Flag[]>('/config/flags'),
  });
  const [pending, setPending] = useState<Flag | null>(null);
  const save = useMutation({
    mutationFn: (f: Flag) =>
      api(`/config/flags/${f.key}`, {
        method: 'PATCH',
        body: JSON.stringify({
          enabled: !f.enabled,
          reason: 'Changed on the employer portal settings page',
        }),
      }),
    onSuccess: () => {
      toast.success('Setting saved.');
      setPending(null);
      void qc.invalidateQueries({ queryKey: ['flags'] });
    },
    onError: (e) => {
      setPending(null);
      toast.error(e instanceof ApiError ? e.message : 'Could not save.');
    },
  });
  const rows = (q.data ?? []).filter((f) => f.key in PORTAL);

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Employer portal settings | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Administration', to: '/administration' },
          { label: 'Employer portal' },
        ]}
        title="Employer portal settings"
        description="How much freedom employer users have. Each change is recorded in the audit trail."
      />
      {q.isError && (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      )}
      {q.isPending && <LoadingState />}
      {rows.length > 0 && (
        <Section title="Settings" flush>
          <ul className="divide-y">
            {rows.map((f) => {
              const t = PORTAL[f.key];
              return (
                <li
                  key={f.key}
                  className="flex items-start justify-between gap-6 p-5"
                >
                  <div>
                    <p className="font-medium" id={`flag-${f.key}`}>
                      {t.title}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {f.enabled ? t.on : t.off}
                    </p>
                  </div>
                  <Switch
                    aria-labelledby={`flag-${f.key}`}
                    checked={f.enabled}
                    disabled={!canManage || save.isPending}
                    onCheckedChange={() => setPending(f)}
                  />
                </li>
              );
            })}
          </ul>
        </Section>
      )}
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={pending ? `Change “${PORTAL[pending.key].title}”?` : ''}
        description={
          pending
            ? pending.enabled
              ? PORTAL[pending.key].off
              : PORTAL[pending.key].on
            : ''
        }
        confirmLabel="Change setting"
        onConfirm={() => pending && save.mutate(pending)}
      />
    </div>
  );
}
