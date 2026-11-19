import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { errorText } from '@/pages/cases/case-shared';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FormModal } from '@/components/shared/modals';
import type { Detail } from './types';

/** Provisional statuses (D-015): the data protection lead may change them. */
const STATUSES = [
  ['not_recorded', 'Not recorded'],
  ['given', 'Given'],
  ['declined', 'Declined'],
  ['withdrawn', 'Withdrawn'],
] as const;

/** Privacy notice and consent (T-054). Only a flag: nothing is blocked when consent is missing. */
export function ConsentCard({
  p,
  consent,
}: {
  p: Detail;
  consent: NonNullable<Detail['consent']>;
}) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<string>(consent.status);
  const [version, setVersion] = useState(consent.notice_version);
  const [on, setOn] = useState(consent.recorded_on ?? '');
  const [error, setError] = useState('');

  const save = useMutation({
    mutationFn: () =>
      api(`/participants/${p.id}/consent`, {
        method: 'PUT',
        body: JSON.stringify({
          status,
          notice_version: version.trim(),
          ...(on ? { recorded_on: on } : {}),
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['participant'] });
      qc.invalidateQueries({ queryKey: ['participants'] });
      setOpen(false);
    },
    onError: (e) => setError(errorText(e)),
  });

  const missing = consent.status === 'not_recorded';
  const needsVersion = status !== 'not_recorded';
  return (
    <Card>
      <CardHeader>
        <CardTitle>Privacy notice and consent</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={missing ? 'warning' : 'secondary'}>
            {consent.label}
          </Badge>
          {consent.notice_version && (
            <span>Notice version {consent.notice_version}</span>
          )}
          {consent.recorded_on && (
            <span className="text-muted-foreground">
              on {consent.recorded_on}
            </span>
          )}
        </div>
        {missing && (
          <p className="text-muted-foreground">
            Consent has not been recorded for this youth. Nothing is blocked,
            but they are flagged in the list and in exports.
          </p>
        )}
        {can('participants.edit') && (
          <Button
            variant="outline"
            onClick={() => {
              setStatus(consent.status);
              setVersion(consent.notice_version);
              setOn(consent.recorded_on ?? '');
              setError('');
              setOpen(true);
            }}
          >
            Record consent
          </Button>
        )}
        <FormModal
          open={open}
          onOpenChange={setOpen}
          title="Record consent"
          description="Which privacy notice the youth was shown and what they decided. The wording of these statuses is provisional."
          pending={save.isPending}
          error={error}
          onSubmit={() => {
            if (needsVersion && !version.trim()) {
              setError('Say which notice version.');
              return;
            }
            setError('');
            save.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="consent-status">Consent status</Label>
            <select
              id="consent-status"
              className="block h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {STATUSES.map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          {needsVersion && (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="consent-version">Privacy notice version</Label>
                <Input
                  id="consent-version"
                  value={version}
                  maxLength={40}
                  onChange={(e) => setVersion(e.target.value)}
                  placeholder="e.g. 2026-01"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="consent-date">Date (today if empty)</Label>
                <Input
                  id="consent-date"
                  type="date"
                  value={on}
                  onChange={(e) => setOn(e.target.value)}
                />
              </div>
            </>
          )}
        </FormModal>
      </CardContent>
    </Card>
  );
}
