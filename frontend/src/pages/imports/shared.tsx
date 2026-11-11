import { Check } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
  Stepper,
  StepperIndicator,
  StepperItem,
  StepperNav,
  StepperSeparator,
  StepperTitle,
} from '@/components/ui/stepper';

// Planning doc 15 §3 describes eight steps. Six are built: cohort defaults (4) and field-by-field
// match review (6) need backend support that waits on D-059 (update vs add) and D-050.
export const STEPS = [
  'Upload',
  'Map columns',
  'Validate and review',
  'Approve',
  'Load',
  'Reconcile',
];

export interface Template {
  id: string;
  source: string;
  version: number;
  target?: string;
  columns: Record<string, string>;
}
export interface Inspection {
  headers: string[];
  row_count: number;
  empty_columns: string[];
  suggested: Record<string, string>;
  fields: { field: string; required: boolean }[];
  matching_templates: string[];
  sample: Record<string, string>;
  reference_codes: Record<
    string,
    { code: string; name: string; programme?: string }[]
  >;
  already_loaded: boolean;
  target?: string;
  defaultable?: string[];
}
export interface Batch {
  id: string;
  file_name: string;
  status: string;
  template: string;
  target?: string;
  counts: {
    total?: number;
    create?: number;
    update?: number;
    held?: number;
    skip?: number;
    warnings?: number;
  };
  reference_plan: { kind: string; label: string }[];
  duplicate_of: string | null;
  created_at: string;
  committed_at: string | null;
}
export interface Reconciliation {
  source_rows: number;
  created: number;
  updated: number;
  skipped: number;
  held: number;
  pending: number;
  rolled_back: number;
  accounted_for: number;
  balanced: boolean;
  quarantined: number;
  controls: {
    cohort: string;
    source: number;
    pi360: number;
    matches: boolean;
  }[];
  controls_match: boolean;
  held_rows: { row: number; reasons: string[] }[];
}

export function ImportStepper({ current }: { current: number }) {
  return (
    <Stepper
      value={current}
      indicators={{ completed: <Check className="size-3.5" /> }}
      className="w-full"
    >
      <StepperNav className="flex-wrap gap-y-2">
        {STEPS.map((title, i) => (
          <StepperItem key={title} step={i + 1}>
            <div className="flex items-center gap-2">
              <StepperIndicator>{i + 1}</StepperIndicator>
              <StepperTitle
                className={
                  i + 1 === current ? 'font-semibold' : 'text-muted-foreground'
                }
              >
                {title}
              </StepperTitle>
            </div>
            {i < STEPS.length - 1 && (
              <StepperSeparator className="mx-3 min-w-4" />
            )}
          </StepperItem>
        ))}
      </StepperNav>
    </Stepper>
  );
}

const TONE: Record<
  string,
  'success' | 'warning' | 'info' | 'secondary' | 'destructive'
> = {
  committed: 'success',
  partially_committed: 'warning',
  validated: 'info',
  approved: 'info',
  committing: 'info',
  rolled_back: 'secondary',
  cancelled: 'secondary',
  rejected: 'destructive',
  uploaded: 'secondary',
};

export function StatusBadge({ status }: { status: string }) {
  const label = status.replace(/_/g, ' ');
  return (
    <Badge variant={TONE[status] ?? 'secondary'} appearance="light">
      {label.charAt(0).toUpperCase() + label.slice(1)}
    </Badge>
  );
}
