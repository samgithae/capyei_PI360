import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
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
import { Textarea } from '@/components/ui/textarea';
import { PageHeader } from '@/components/shared/page-header';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';

export interface Registration {
  id: string;
  name: string;
  date_of_birth: string;
  email: string;
  phone: string;
  programme_code: string;
  enrollment_no: string;
  email_verified: boolean;
  phone_verified: boolean;
  status: string;
  status_label: string;
  possible_duplicate: boolean;
  reviewed_by: string;
  decision_reason: string;
  created_at: string;
}
export interface RegistrationQueue {
  total: number;
  counts: Record<string, number>;
  results: Registration[];
}

const FILTERS = [
  ['', 'All'],
  ['pending_verification', 'Waiting for verification'],
  ['verified', 'Verified'],
  ['under_review', 'Needs review'],
  ['rejected', 'Rejected'],
  ['expired', 'Expired'],
] as const;

const errorText = (e: unknown) =>
  e instanceof ApiError ? e.message : 'Something went wrong.';

interface Match {
  id: string;
  name: string;
  status: string;
  county: string;
  projects: string[];
  reasons: { code: string; text: string }[];
}

interface DecisionResult {
  invite?: { sent: boolean; reason: string; message?: string };
}

const INVITE_NOTE: Record<string, string> = {
  already_has_account:
    'This youth already has an account, so no new invitation was sent.',
  mail_failed:
    'Saved, but the invitation e-mail could not be sent. Send it from the youth’s page.',
  refused:
    'Saved, but the invitation could not be sent. Send it from the youth’s page.',
  unverified_email: 'No invitation sent: the e-mail was not confirmed.',
  record_unavailable: 'No invitation sent: the youth record is not available.',
};

/** Officer review (NEW-046): who on file looks like this person, then link to them or make a
 * new record. Both need a reason; making a new record when someone similar exists also needs a
 * tick to say you looked. */
function ReviewPanel({
  r,
  onDone,
}: {
  r: Registration;
  onDone: (res: DecisionResult) => void;
}) {
  const { can } = useAuth();
  const [reason, setReason] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState('');
  const matches = useQuery({
    queryKey: ['registrations', r.id, 'matches'],
    queryFn: () => api<{ matches: Match[] }>(`/registrations/${r.id}/matches`),
    retry: false,
  });
  const found = matches.data?.matches ?? [];
  const decide = useMutation({
    mutationFn: (v: { path: string; body: object }) =>
      post<DecisionResult>(`/registrations/${r.id}/${v.path}`, v.body),
    onSuccess: onDone,
    onError: (e) => setError(errorText(e)),
  });
  const go = (path: string, body: object) => {
    setError('');
    decide.mutate({ path, body: { reason, ...body } });
  };
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Who is already on file?</h3>
      {matches.isLoading && <LoadingState />}
      {matches.isSuccess && found.length === 0 && (
        <p className="text-sm">No one similar was found.</p>
      )}
      {found.map((m) => (
        <div
          key={m.id}
          className="flex items-center justify-between gap-2 rounded border p-2 text-sm"
        >
          <div>
            <span className="font-medium">{m.name}</span>
            {m.county && ` · ${m.county}`}
            {m.projects.length > 0 && ` · ${m.projects.join(', ')}`}
            <p className="text-xs text-muted-foreground">
              {m.reasons.map((x) => x.text).join('; ')}
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            disabled={decide.isPending}
            aria-label={`Link to ${m.name}`}
            onClick={() => go('link', { participant_id: m.id })}
          >
            Link to this person
          </Button>
        </div>
      ))}
      <Textarea
        aria-label={`Reason for deciding ${r.name}`}
        placeholder="Why this decision? (required)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      {found.length > 0 && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={confirm}
            onChange={(e) => setConfirm(e.target.checked)}
          />
          I have looked, and this is a different person.
        </label>
      )}
      {can('participants.edit') && (
        <Button
          size="sm"
          disabled={decide.isPending}
          onClick={() => go('create', { confirm_similar: confirm })}
        >
          Create a new record
        </Button>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function Row({ r }: { r: Registration }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [inviteNote, setInviteNote] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const done = () => qc.invalidateQueries({ queryKey: ['registrations'] });
  const reject = useMutation({
    mutationFn: () => post(`/registrations/${r.id}/reject`, { reason }),
    onSuccess: () => {
      setRejecting(false);
      setReason('');
      done();
    },
    onError: (e) => setError(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: () => api(`/registrations/${r.id}`, { method: 'DELETE' }),
    onSuccess: done,
    onError: (e) => setError(errorText(e)),
  });
  const settled = r.status === 'approved_new' || r.status === 'linked_existing';
  const deletable = r.status === 'rejected' || r.status === 'expired';
  return (
    <>
      <TableRow>
        <TableCell className="font-medium">{r.name}</TableCell>
        <TableCell>{r.date_of_birth}</TableCell>
        <TableCell>
          {r.email}
          {r.email && !r.email_verified && ' (not verified)'}
          {r.email && r.phone && <br />}
          {r.phone}
          {r.phone && !r.phone_verified && ' (not verified)'}
        </TableCell>
        <TableCell>
          {[r.programme_code, r.enrollment_no].filter(Boolean).join(' / ')}
        </TableCell>
        <TableCell>
          <Badge variant="outline">{r.status_label}</Badge>
          {r.possible_duplicate && (
            <Badge className="ml-1">Possible duplicate</Badge>
          )}
          {r.decision_reason && (
            <p className="text-xs text-muted-foreground">{r.decision_reason}</p>
          )}
          {inviteNote && (
            <p className="text-xs" role="status">
              {inviteNote}
            </p>
          )}
        </TableCell>
        <TableCell className="space-x-2 text-right">
          {(r.status === 'verified' || r.status === 'under_review') && (
            <Button size="sm" onClick={() => setReviewing((v) => !v)}>
              Review
            </Button>
          )}
          {!settled && r.status !== 'rejected' && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setRejecting(true)}
            >
              Reject
            </Button>
          )}
          {deletable && can('config.manage') && (
            <Button
              size="sm"
              variant="outline"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Delete
            </Button>
          )}
        </TableCell>
      </TableRow>
      {reviewing && (
        <TableRow>
          <TableCell colSpan={6}>
            <ReviewPanel
              r={r}
              onDone={(res) => {
                setReviewing(false);
                setInviteNote(
                  res.invite?.sent
                    ? 'Invitation sent to the e-mail address they confirmed.'
                    : (INVITE_NOTE[res.invite?.reason ?? ''] ?? ''),
                );
                done();
              }}
            />
          </TableCell>
        </TableRow>
      )}
      {(rejecting || error) && (
        <TableRow>
          <TableCell colSpan={6} className="space-y-2">
            {rejecting && (
              <>
                <Textarea
                  aria-label={`Reason for rejecting ${r.name}`}
                  placeholder="Why is this request being rejected?"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={reject.isPending}
                    onClick={() => {
                      setError('');
                      reject.mutate();
                    }}
                  >
                    Confirm rejection
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setRejecting(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </>
            )}
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

export function RegistrationsPage() {
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const query = useQuery({
    queryKey: ['registrations', status, search],
    queryFn: () =>
      api<RegistrationQueue>(
        `/registrations?status=${encodeURIComponent(status)}&search=${encodeURIComponent(search)}`,
      ),
    retry: false,
  });
  const off = query.error instanceof ApiError && query.error.status === 404;
  return (
    <div className="space-y-4">
      <Helmet>
        <title>Self-registrations</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Participants' }, { label: 'Self-registrations' }]}
        title="Self-registrations"
        description="Youth who signed themselves up. Nothing here is a youth record until it is approved or linked to one."
      />
      {off ? (
        <EmptyState
          title="Self-registration is switched off"
          hint="An administrator can turn on the portal.self_registration feature flag when CAP-YEI has approved the consent wording."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {FILTERS.map(([value, label]) => (
              <Button
                key={value}
                size="sm"
                variant={status === value ? 'primary' : 'outline'}
                onClick={() => setStatus(value)}
              >
                {label}
                {value && query.data?.counts[value]
                  ? ` (${query.data.counts[value]})`
                  : ''}
              </Button>
            ))}
            <Input
              className="w-64"
              aria-label="Search registrations"
              placeholder="Search name, e-mail or phone"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {query.isLoading ? (
            <LoadingState />
          ) : query.isError ? (
            <ErrorState error={query.error} onRetry={() => query.refetch()} />
          ) : query.data!.results.length === 0 ? (
            <EmptyState title="No self-registrations" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Date of birth</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Programme / number</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data!.results.map((r) => (
                  <Row key={r.id} r={r} />
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </div>
  );
}
