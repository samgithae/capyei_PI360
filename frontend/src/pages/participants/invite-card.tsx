import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { DataCard } from '@/components/data-card';
import { SelectField } from '@/components/shared/select-field';

interface InviteState {
  state: 'none' | 'pending' | 'active';
  invited_at?: string;
  expires_at?: string;
  expired?: boolean;
  consented_at?: string | null;
  emails: string[];
}

/** Staff: invite a youth to sign in, using an e-mail address already on their record. */
export function InviteCard({ id }: { id: string }) {
  const qc = useQueryClient();
  const key = ['participant-invite', id];
  const q = useQuery({
    queryKey: key,
    queryFn: () => api<InviteState>(`/participants/${id}/invite`),
  });
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const done = (s: InviteState) => {
    qc.setQueryData(key, s);
    setError('');
  };
  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : 'Something went wrong.');
  const send = useMutation({
    mutationFn: (to: string) =>
      post<InviteState>(`/participants/${id}/invite`, { email: to }),
    onSuccess: done,
    onError: fail,
  });
  const withdraw = useMutation({
    mutationFn: () =>
      api<InviteState>(`/participants/${id}/invite`, { method: 'DELETE' }),
    onSuccess: done,
    onError: fail,
  });

  const s = q.data;
  if (!s) return null;
  const chosen = email || s.emails[0] || '';
  const day = (d?: string) => (d ? new Date(d).toLocaleDateString() : '');

  return (
    <DataCard title="Youth sign-in">
      <div className="space-y-3 p-5 text-sm">
        {s.state === 'active' && (
          <p>
            This youth has an account and can sign in to see and add to their
            own record.
            {s.consented_at ? ` Consent given ${day(s.consented_at)}.` : ''}
          </p>
        )}
        {s.state === 'pending' && (
          <p>
            Invite sent {day(s.invited_at)}.{' '}
            {s.expired
              ? 'The link has expired. Send a new one.'
              : `The link works until ${day(s.expires_at)}.`}
          </p>
        )}
        {s.state === 'none' && (
          <p className="text-muted-foreground">
            Send a one-time link so this youth can sign in and add their own
            skills and availability. Nothing they add is treated as checked
            until staff verify it.
          </p>
        )}
        {s.state !== 'active' &&
          (s.emails.length === 0 ? (
            <p className="text-muted-foreground">
              There is no e-mail address on this record, or you cannot see
              contact details. Add one first.
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <SelectField
                label="E-mail address to invite"
                className="w-72"
                value={chosen}
                options={s.emails.map((e) => ({ id: e, name: e }))}
                onChange={setEmail}
              />
              <Button
                size="sm"
                disabled={send.isPending || !chosen}
                onClick={() => send.mutate(chosen)}
              >
                {s.state === 'pending' ? 'Send a new invite' : 'Send invite'}
              </Button>
              {s.state === 'pending' && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={withdraw.isPending}
                  onClick={() => withdraw.mutate()}
                >
                  Withdraw invite
                </Button>
              )}
            </div>
          ))}
        {error && (
          <p role="alert" className="text-destructive">
            {error}
          </p>
        )}
      </div>
    </DataCard>
  );
}
