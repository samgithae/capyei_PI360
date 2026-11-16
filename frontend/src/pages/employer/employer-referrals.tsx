import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import {
  CandidateProfile,
  WhySuggested,
} from '@/pages/referrals/candidate-profile';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams, useSearchParams } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
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
import { Textarea } from '@/components/ui/textarea';
import {
  DataCard,
  FilterSelect,
  Pager,
  SearchBox,
} from '@/components/data-card';
import { DetailList, Section } from '@/components/shared/info-card';
import { FormModal } from '@/components/shared/modals';
import { PageHeader } from '@/components/shared/page-header';
import { SelectField } from '@/components/shared/select-field';
import { StatusBadge } from '@/components/shared/status-badge';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
} from '@/components/states';
import {
  REFERRAL_VIEW_LABELS,
  type OpportunityPage,
  type ReferralPage,
  type ReferralRow,
} from './employer-types';

const STAGES = [
  { id: 'submitted', name: 'New' },
  { id: 'under_review', name: 'Under review' },
  { id: 'interview', name: 'Interview' },
  { id: 'selected', name: 'Selected' },
  { id: 'placed', name: 'Placed' },
  { id: 'rejected', name: 'Declined' },
];

/** What each move is called on the button. The server decides which are allowed. */
const MOVE_LABEL: Record<string, string> = {
  under_review: 'Start review',
  interview: 'Invite to interview',
  selected: 'Select',
  rejected: 'Decline',
};

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString() : '';
const day = (iso: string | null) => (iso ? iso.slice(0, 10) : '');

interface HistoryItem {
  to: string;
  label: string;
  at: string;
  by: string;
  own: boolean;
  reason: string;
  note: string;
}
interface Detail extends ReferralRow {
  interview: { at: string | null; place: string; note: string };
  can_move_to: string[];
  can_set_interview: boolean;
  contact_visible: boolean;
  history: HistoryItem[];
}
interface Reason {
  id: string;
  name: string;
  needs_note: boolean;
}

function useRefresh(id?: string) {
  const qc = useQueryClient();
  return () => {
    if (id) void qc.invalidateQueries({ queryKey: ['employer-referral', id] });
    void qc.invalidateQueries({ queryKey: ['employer-referrals'] });
    void qc.invalidateQueries({ queryKey: ['employer-dashboard'] });
  };
}

export function EmployerReferralsPage() {
  const [params, setParams] = useSearchParams();
  const q = useQuery({
    queryKey: ['employer-referrals', params.toString()],
    queryFn: () =>
      api<ReferralPage>(`/employer/referrals?${params.toString()}`),
  });
  const opps = useQuery({
    queryKey: ['employer-opportunities', 'choices'],
    queryFn: () =>
      api<OpportunityPage>('/employer/opportunities?page_size=100'),
    staleTime: 60_000,
  });
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('offset');
    setParams(next);
  };
  const data = q.data;
  const view = params.get('view') ?? '';
  const offset = Number(params.get('offset') ?? 0);
  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Referrals | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Referrals' }]}
        title="Referrals"
        description="Young people PI 360 has put forward for your opportunities."
      />
      {view && REFERRAL_VIEW_LABELS[view] && (
        <Notice title={`Showing: ${REFERRAL_VIEW_LABELS[view]}`}>
          <button
            type="button"
            className="text-primary underline"
            onClick={() => set('view', '')}
          >
            Show all referrals
          </button>
        </Notice>
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
              placeholder="Search by name or opportunity"
              defaultValue={params.get('q') ?? ''}
              onSubmit={(v) => set('q', v)}
            />
            <FilterSelect
              label="Any stage"
              value={params.get('stage') ?? ''}
              options={STAGES}
              onChange={(v) => set('stage', v)}
              className="w-44"
            />
            <FilterSelect
              label="Any opportunity"
              value={params.get('opportunity') ?? ''}
              options={(opps.data?.results ?? []).map((o) => ({
                id: o.id,
                name: o.title,
              }))}
              onChange={(v) => set('opportunity', v)}
              className="w-56"
            />
          </>
        }
      >
        {q.isError && (
          <div className="p-5">
            <ErrorState error={q.error} onRetry={() => void q.refetch()} />
          </div>
        )}
        {q.isPending && (
          <div className="p-5">
            <LoadingState />
          </div>
        )}
        {data && data.results.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Candidate</TableHead>
                <TableHead>Opportunity</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Referred</TableHead>
                <TableHead>Interview</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-foreground hover:text-primary"
                      to={`/employer/referrals/${r.id}`}
                    >
                      {r.candidate}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Link
                      className="hover:text-primary"
                      to={`/employer/opportunities/${r.opportunity_id}`}
                    >
                      {r.opportunity}
                    </Link>
                  </TableCell>
                  <TableCell className="space-x-2">
                    <StatusBadge status={r.stage} label={r.stage_label} />
                    {r.needs_action && (
                      <Badge variant="warning" appearance="light">
                        Needs your reply
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>{day(r.referred_at)}</TableCell>
                  <TableCell>{when(r.interview_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {data && data.results.length === 0 && (
          <div className="p-5">
            <EmptyState
              title="No referrals match"
              hint="Referrals appear here when PI 360 puts a young person forward."
            />
          </div>
        )}
      </DataCard>
    </div>
  );
}

/** The interview's time, place and a note for the candidate, saved to the company's own route. */
function InterviewCard({
  id,
  interview,
  onSaved,
}: {
  id: string;
  interview: Detail['interview'];
  onSaved: () => void;
}) {
  const toLocal = (iso: string | null) => {
    if (!iso) return '';
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };
  const [at, setAt] = useState(toLocal(interview.at));
  const [place, setPlace] = useState(interview.place);
  const [note, setNote] = useState(interview.note);
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () =>
      post(`/employer/referrals/${id}/interview`, {
        at: new Date(at).toISOString(),
        place,
        note,
      }),
    onSuccess: () => {
      toast.success('Interview details saved.');
      setError('');
      onSaved();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Something went wrong.'),
  });
  return (
    <Section
      title="Interview details"
      description="PI 360 passes these on to the candidate. Say what to bring and who to ask for."
    >
      <div className="space-y-3 p-5">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="ei-at">Date and time</Label>
            <Input
              id="ei-at"
              type="datetime-local"
              value={at}
              onChange={(e) => setAt(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ei-place">Place</Label>
            <Input
              id="ei-place"
              maxLength={200}
              value={place}
              onChange={(e) => setPlace(e.target.value)}
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="ei-note">Note for the candidate</Label>
          <Input
            id="ei-note"
            maxLength={500}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button disabled={!at || save.isPending} onClick={() => save.mutate()}>
          Save interview details
        </Button>
      </div>
    </Section>
  );
}

export function EmployerReferralPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const refresh = useRefresh(id);
  const canRespond = can('employer.respond_referrals');
  const [moving, setMoving] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const q = useQuery({
    queryKey: ['employer-referral', id],
    queryFn: () => api<Detail>(`/employer/referrals/${id}`),
    retry: false,
  });
  const reasons = useQuery({
    queryKey: ['employer-referral-reasons'],
    queryFn: () =>
      api<{ results: Reason[] }>('/employer/referral-reasons').then(
        (r) => r.results,
      ),
    enabled: moving === 'rejected',
  });
  const move = useMutation({
    mutationFn: () =>
      post(`/employer/referrals/${id}/transition`, {
        to: moving,
        reason_id: reason || null,
        note,
      }),
    onSuccess: () => {
      toast.success('Your reply has been recorded.');
      setMoving(null);
      refresh();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Something went wrong.'),
  });

  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Referral not found"
            hint="It may belong to another company, or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        )}
        <Link className="text-primary" to="/employer/referrals">
          Back to referrals
        </Link>
      </div>
    );
  }
  const r = q.data;
  if (!r) return <LoadingState />;

  const picked = reasons.data?.find((x) => x.id === reason);
  const rejecting = moving === 'rejected';
  const open = (to: string) => {
    setMoving(to);
    setReason('');
    setNote('');
    setError('');
  };
  return (
    <div className="container-fluid space-y-6">
      <Helmet>
        <title>{`${r.candidate} | PI 360`}</title>
      </Helmet>
      <PageHeader
        crumbs={[
          { label: 'Referrals', to: '/employer/referrals' },
          { label: r.candidate },
        ]}
        title={`${r.candidate} for ${r.opportunity}`}
        badges={<StatusBadge status={r.stage} label={r.stage_label} />}
        meta={
          <>
            <Link
              className="text-primary hover:underline"
              to={`/employer/opportunities/${r.opportunity_id}`}
            >
              {r.opportunity}
            </Link>
            <span>Referred {day(r.referred_at)}</span>
          </>
        }
        actions={
          canRespond &&
          r.can_move_to.map((to) => (
            <Button
              key={to}
              variant={to === 'rejected' ? 'outline' : 'primary'}
              onClick={() => open(to)}
            >
              {MOVE_LABEL[to] ?? to}
            </Button>
          ))
        }
      />
      {r.contact_visible ? (
        <Notice title="You selected this candidate">
          Their phone number and email are in the CV below.
        </Notice>
      ) : (
        <Notice title="Contact details are shared once you select the candidate">
          Until then PI 360 stays in touch with the candidate for you.
        </Notice>
      )}
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          {r.can_set_interview && canRespond && (
            <InterviewCard
              key={r.interview.at ?? 'new'}
              id={r.id}
              interview={r.interview}
              onSaved={refresh}
            />
          )}
          <WhySuggested
            id={r.id}
            origin="officer"
            path={`/employer/referrals/${r.id}/why`}
          />
          <CandidateProfile
            participantId={r.id}
            fullProfile={false}
            description="The CV PI 360 shares with you. Download it to keep a copy."
            paths={{
              cv: `/employer/referrals/${r.id}/cv`,
              pdf: `/employer/referrals/${r.id}/cv.pdf`,
              photo: `/employer/referrals/${r.id}/photo`,
            }}
          />
        </div>
        <div className="space-y-5">
          <Section title="Overview">
            <DetailList
              items={[
                {
                  label: 'Stage',
                  value: <StatusBadge status={r.stage} label={r.stage_label} />,
                },
                { label: 'Opportunity', value: r.opportunity },
                { label: 'Referred', value: when(r.referred_at) },
                { label: 'Interview', value: when(r.interview.at) },
                { label: 'Place', value: r.interview.place },
              ]}
            />
          </Section>
          <Section title="History">
            {r.history.length === 0 ? (
              <EmptyState title="No changes yet" />
            ) : (
              <ol className="space-y-4 p-5">
                {r.history.map((h, i) => (
                  <li key={`${h.at}-${i}`} className="text-sm">
                    <p className="font-medium">{h.label}</p>
                    {h.reason && (
                      <p className="text-xs text-muted-foreground">
                        Reason: {h.reason}
                      </p>
                    )}
                    {h.note && <p>{h.note}</p>}
                    <p className="text-xs text-muted-foreground">
                      {h.by} · {when(h.at)}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </Section>
        </div>
      </div>

      <FormModal
        open={moving !== null}
        onOpenChange={(o) => !o && setMoving(null)}
        title={moving ? (MOVE_LABEL[moving] ?? moving) : ''}
        description={
          rejecting
            ? 'Say why. PI 360 uses this to find better matches.'
            : undefined
        }
        submitLabel="Confirm"
        pending={move.isPending}
        error={error}
        onSubmit={() => {
          if (rejecting && !reason) return setError('Choose a reason.');
          if (rejecting && picked?.needs_note && !note.trim())
            return setError('Add a note saying what happened.');
          setError('');
          move.mutate();
        }}
      >
        {rejecting && (
          <div className="space-y-1.5">
            <Label>
              Reason <span className="text-destructive">*</span>
            </Label>
            <SelectField
              label="Choose a reason"
              value={reason}
              options={reasons.data ?? []}
              onChange={setReason}
            />
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="er-note">Note</Label>
          <Textarea
            id="er-note"
            maxLength={2000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
      </FormModal>
    </div>
  );
}
