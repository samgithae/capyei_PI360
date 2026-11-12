import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';

// Shapes returned by /api/v1/referrals (backend: apps/referrals/views.py).
export interface ReferralRow {
  id: string;
  participant_id: string;
  participant: string;
  opportunity_id: string;
  opportunity: string;
  employer: string;
  origin: string;
  stage: string;
  stage_label: string;
  reason: string;
  assigned_to: string;
  assigned_to_id: number | null;
  referred_at: string | null;
  closed_at: string | null;
  updated_at: string;
}
export interface ReferralPage {
  total: number;
  page_size: number;
  results: ReferralRow[];
}
export interface StageEvent {
  id: number;
  kind: 'transition' | 'correction';
  from: string;
  to: string;
  reason: string;
  note: string;
  corrects: number | null;
  actor: string;
  at: string;
}
export interface ReferralDetail extends ReferralRow {
  reason_id: string | null;
  reason_note: string;
  interview_at: string | null;
  interview_place: string;
  interview_note: string;
  created_by: string;
  created_at: string;
  next_stages: string[];
  unsuccessful: string[];
  history: StageEvent[];
  can: { edit: boolean; reopen: boolean; reassign: boolean };
}
export interface Reason {
  id: string;
  code: string;
  name: string;
  applies_to: string;
  needs_note: boolean;
}

// Same order and wording as Referral.STAGES on the server.
export const STAGES: { id: string; name: string }[] = [
  { id: 'draft', name: 'Draft' },
  { id: 'submitted', name: 'Submitted' },
  { id: 'under_review', name: 'Under review' },
  { id: 'interview', name: 'Interview or assessment' },
  { id: 'selected', name: 'Selected' },
  { id: 'rejected', name: 'Rejected' },
  { id: 'withdrawn', name: 'Withdrawn' },
  { id: 'no_response', name: 'No response' },
  { id: 'placed', name: 'Placed' },
  { id: 'closed', name: 'Closed' },
];
export const stageName = (id: string) =>
  STAGES.find((s) => s.id === id)?.name ?? id;
export const UNSUCCESSFUL = ['rejected', 'withdrawn', 'no_response'];
export const ACTIVE = [
  'draft',
  'submitted',
  'under_review',
  'interview',
  'selected',
];

/** Every query a referral change can make stale, so lists and counts refresh. */
export function useRefreshReferrals() {
  const qc = useQueryClient();
  return () => {
    for (const key of [
      'referral',
      'referral-history',
      'referrals',
      'opportunity-suggestions',
    ])
      void qc.invalidateQueries({ queryKey: [key] });
    void qc.invalidateQueries({ queryKey: ['referral-summary'] });
  };
}

interface Picked {
  id: string;
  name: string;
}

/** "Refer youth" dialog. Pass the youth (from the profile) or the opportunity (from the
 * opportunity page) to fix one side; the other is searched. With neither, both are searched. */
export function ReferDialog({
  open,
  onOpenChange,
  participant,
  opportunity,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  participant?: Picked;
  opportunity?: Picked;
}) {
  const nav = useNavigate();
  const refresh = useRefreshReferrals();
  const [youthQ, setYouthQ] = useState('');
  const [oppQ, setOppQ] = useState('');
  const [youthId, setYouthId] = useState('');
  const [oppId, setOppId] = useState('');
  const [note, setNote] = useState('');
  const [draft, setDraft] = useState(false);
  const [error, setError] = useState('');

  // Only the side that is not fixed needs a search. `enabled` keeps the query idle
  // until the dialog is open, so pages that never open it make no request.
  const youth = useQuery({
    queryKey: ['refer-youth', youthQ],
    queryFn: () =>
      api<{ results: { id: string; name: string }[] }>(
        `/participants?q=${encodeURIComponent(youthQ)}`,
      ),
    enabled: open && !participant,
  });
  const opps = useQuery({
    queryKey: ['refer-opportunities', oppQ],
    queryFn: () =>
      api<{ results: { id: string; title: string; employer: string }[] }>(
        `/opportunities?status=open&q=${encodeURIComponent(oppQ)}`,
      ),
    enabled: open && !opportunity,
  });

  const close = (o: boolean) => {
    onOpenChange(o);
    if (!o) {
      setError('');
      setNote('');
      setDraft(false);
    }
  };
  const create = useMutation({
    mutationFn: () =>
      post<{ id: string }>('/referrals', {
        participant_id: participant?.id ?? youthId,
        opportunity_id: opportunity?.id ?? oppId,
        note,
        submit: !draft,
      }),
    onSuccess: (r) => {
      toast.success(draft ? 'Referral saved as a draft.' : 'Referral sent.');
      refresh();
      close(false);
      nav(`/referrals/${r.id}`);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save.'),
  });

  return (
    <FormModal
      open={open}
      onOpenChange={close}
      title="Refer youth"
      description="Put one youth forward for one open opportunity. Every stage change is kept in the referral's history."
      submitLabel={draft ? 'Save draft' : 'Send referral'}
      pending={create.isPending}
      error={error}
      onSubmit={() => {
        if (!participant && !youthId) return setError('Choose a youth.');
        if (!opportunity && !oppId) return setError('Choose an opportunity.');
        setError('');
        create.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="refer-youth">
          Youth <span className="text-destructive">*</span>
        </Label>
        {participant ? (
          <p id="refer-youth" className="text-sm font-medium">
            {participant.name}
          </p>
        ) : (
          <>
            <Input
              id="refer-youth"
              placeholder="Search youth by name"
              value={youthQ}
              onChange={(e) => setYouthQ(e.target.value)}
            />
            <SelectField
              label="Choose youth"
              value={youthId}
              options={youth.data?.results ?? []}
              onChange={setYouthId}
            />
          </>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="refer-opportunity">
          Opportunity <span className="text-destructive">*</span>
        </Label>
        {opportunity ? (
          <p id="refer-opportunity" className="text-sm font-medium">
            {opportunity.name}
          </p>
        ) : (
          <>
            <Input
              id="refer-opportunity"
              placeholder="Search open opportunities by title"
              value={oppQ}
              onChange={(e) => setOppQ(e.target.value)}
            />
            <SelectField
              label="Choose opportunity"
              value={oppId}
              options={(opps.data?.results ?? []).map((o) => ({
                id: o.id,
                name: `${o.title} (${o.employer})`,
              }))}
              onChange={setOppId}
            />
          </>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="refer-note">Why this youth (optional)</Label>
        <Textarea
          id="refer-note"
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          aria-label="Save as a draft"
          checked={draft}
          onCheckedChange={(v) => setDraft(v === true)}
        />
        Save as a draft (send it later)
      </label>
    </FormModal>
  );
}
