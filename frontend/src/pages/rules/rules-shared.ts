import { useQueryClient } from '@tanstack/react-query';

// Types for the rules API (T-047). The shapes mirror backend/apps/intelligence/views.py.

export interface VersionSummary {
  id: string;
  number: number;
  status: string;
  status_label: string;
  change_notes: string;
  factors: number;
  waiting: number; // parameters still waiting for a decision
  created_by: string;
  created_at: string | null;
  approved_by: string;
  approved_at: string | null;
  effective_from: string | null;
  retired_at: string | null;
  used: boolean;
}

export interface RuleSet {
  id: string;
  module: string;
  module_label: string;
  code: string;
  name: string;
  purpose: string;
  active: VersionSummary | null;
  latest: VersionSummary | null;
  version_count: number;
}

export interface RuleSetDetail extends RuleSet {
  versions: VersionSummary[];
}

export interface Factor {
  code: string;
  label: string;
  type?: string;
  operator: string;
  field: string;
  value: unknown;
  mandatory?: boolean;
  mandatory_from_requirement?: boolean;
  weight?: number;
  unknown_policy?: string;
  max_age_days?: number;
  enabled?: boolean;
  note?: string;
}

export interface Parameter {
  label?: string;
  value: unknown;
  approved?: boolean;
  decision?: string;
  unit?: string;
  note?: string;
}

export interface Definition {
  factors?: Factor[];
  parameters?: Record<string, Parameter>;
  notes?: string;
}

export type StepName =
  | 'submit'
  | 'return'
  | 'approve'
  | 'activate'
  | 'deactivate'
  | 'clone';

export interface VersionDetail extends VersionSummary {
  rule_set: {
    id: string;
    code: string;
    name: string;
    module: string;
    module_label: string;
  };
  definition: Definition;
  definition_hash: string;
  problems: { path: string; message: string }[];
  unapproved: string[];
  submitted_by: string;
  submitted_at: string | null;
  activated_by: string;
  cloned_from: number | null;
  // What this user may do to this version now (the server decides from status + permission).
  actions: (StepName | 'edit' | 'discard')[];
}

export interface Operator {
  code: string;
  label: string;
  expects: string;
}

export const MODULES = [
  { id: 'A', name: 'Module A: placement support priority' },
  { id: 'B', name: 'Module B: opportunity compatibility' },
  { id: 'C', name: 'Module C: employer reliability' },
];

export const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString() : '';

/** A rule value as text a reviewer can read: 30, "open", [1, 5], {"skill": ...}. */
export function show(value: unknown): string {
  if (value === null || value === undefined) return 'not set';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

/** What a factor is compared with: a fixed value, a parameter, or another field. */
export function expected(f: Factor, d: Definition): string {
  const v = f.value;
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    const ref = v as Record<string, unknown>;
    const keys = Object.keys(ref);
    if (keys.length === 1 && typeof ref.param === 'string') {
      const p = d.parameters?.[ref.param];
      const unit = p?.unit ? ` ${p.unit}` : '';
      return p && p.value !== null && p.value !== undefined
        ? `${show(p.value)}${unit} (parameter ${ref.param})`
        : `parameter ${ref.param}, not decided yet`;
    }
    if (keys.length === 1 && typeof ref.field === 'string')
      return `the value of ${ref.field}`;
  }
  return show(v);
}

/** After any change to a rule version, refetch every rules query (list, set, version, history). */
export function useRefreshRules() {
  const qc = useQueryClient();
  return () =>
    Promise.all(
      ['rules', 'rule-set', 'rule-version', 'rule-version-history'].map((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
    );
}
