import { Badge } from '@/components/ui/badge';

type Tone = 'success' | 'info' | 'warning' | 'secondary' | 'destructive';

// One colour map for every status the application uses (employer, opportunity, participant,
// referral stage).
// Colour is always paired with the status text (NFR-02). Unknown values fall back to neutral,
// so a new backend status never breaks a page; add it here to give it a colour.
const TONE: Record<string, Tone> = {
  active: 'success',
  open: 'success',
  approved: 'success',
  completed: 'info',
  prospect: 'info',
  draft: 'secondary',
  inactive: 'secondary',
  unknown: 'secondary',
  pending: 'warning',
  withdrawn: 'warning',
  closed: 'secondary',
  expired: 'warning',
  rejected: 'destructive',
  // Referral stages (T-046)
  submitted: 'info',
  under_review: 'info',
  interview: 'info',
  selected: 'success',
  placed: 'success',
  no_response: 'warning',
};

/** Status as a light Metronic badge. Use this everywhere instead of hand-picking a variant. */
export function StatusBadge({
  status,
  label,
}: {
  status: string;
  label?: string; // readable text from the API; defaults to the code with spaces
}) {
  return (
    <Badge
      variant={TONE[status] ?? 'secondary'}
      appearance="light"
      className="capitalize"
    >
      {label ?? status.replace(/_/g, ' ')}
    </Badge>
  );
}
