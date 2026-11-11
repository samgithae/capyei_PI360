import { type ComponentType } from 'react';
import {
  Ban,
  Building2,
  CheckCircle2,
  Clock,
  Copy,
  FilePlus2,
  GitMerge,
  ListChecks,
  MoveRight,
  Pencil,
  Power,
  RotateCcw,
  Send,
  Trash2,
  Undo2,
  UserCheck,
  UserMinus,
  UserPlus,
} from 'lucide-react';
import { EmptyState } from '@/components/states';

export interface AuditEvent {
  at: string;
  actor: string;
  action: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  reason?: string;
}

const KNOWN: Record<
  string,
  { label: string; icon: ComponentType<{ className?: string }> }
> = {
  'employer.created': { label: 'Employer created', icon: Building2 },
  'employer.updated': { label: 'Employer details updated', icon: Pencil },
  'employer.contact_added': { label: 'Contact added', icon: UserPlus },
  'employer.contact_updated': { label: 'Contact updated', icon: Pencil },
  'employer.contact_removed': { label: 'Contact removed', icon: UserMinus },
  'opportunity.created': { label: 'Opportunity created', icon: FilePlus2 },
  'opportunity.updated': { label: 'Opportunity updated', icon: Pencil },
  'opportunity.requirement_added': {
    label: 'Requirement added',
    icon: ListChecks,
  },
  'opportunity.requirement_updated': {
    label: 'Requirement updated',
    icon: Pencil,
  },
  'opportunity.requirement_removed': {
    label: 'Requirement removed',
    icon: Trash2,
  },
  'referral.created': { label: 'Referral created', icon: Send },
  'referral.stage_changed': { label: 'Stage changed', icon: MoveRight },
  'referral.corrected': { label: 'Stage corrected', icon: Undo2 },
  'referral.assigned': { label: 'Referral reassigned', icon: UserCheck },
  'rule_set.created': { label: 'Rule set created', icon: FilePlus2 },
  'rule_version.created': { label: 'Draft created', icon: Copy },
  'rule_version.edited': { label: 'Draft edited', icon: Pencil },
  'rule_version.submitted': { label: 'Sent for review', icon: Send },
  'rule_version.returned': { label: 'Returned to draft', icon: Undo2 },
  'rule_version.approved': { label: 'Approved', icon: CheckCircle2 },
  'rule_version.activated': { label: 'Activated', icon: Power },
  'rule_version.retired': {
    label: 'Retired, replaced by a newer version',
    icon: Clock,
  },
  'rule_version.deactivated': { label: 'Deactivated', icon: Ban },
  'rule_version.reactivated': {
    label: 'Back in force after a deactivation',
    icon: RotateCcw,
  },
  'rule_version.discarded': { label: 'Draft discarded', icon: Trash2 },
  'employer.cluster_decided': {
    label: 'Employer match decided',
    icon: GitMerge,
  },
};

function describe(action: string) {
  const known = KNOWN[action];
  if (known) return known;
  // Unknown action (e.g. a status transition): readable fallback from the code name.
  const tail = action.split('.').pop() ?? action;
  const text = tail.replace(/_/g, ' ');
  return {
    label: text.charAt(0).toUpperCase() + text.slice(1),
    icon: Clock,
  };
}

/** Names of the fields that differ between before and after, for the one-line detail. */
function changedFields(e: AuditEvent) {
  const b = e.before ?? {};
  const a = e.after ?? {};
  return Object.keys(a)
    .filter((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k]))
    .map((k) => k.replace(/_/g, ' '));
}

/** Newest-first activity feed built from audit events: icon, what happened, who and when. */
export function ActivityTimeline({ events }: { events: AuditEvent[] }) {
  if (events.length === 0)
    return <EmptyState title="No activity recorded yet" />;
  return (
    <ol className="relative space-y-5 border-s border-border ps-6">
      {events.map((e, i) => {
        const { label, icon: Icon } = describe(e.action);
        const fields = e.action.endsWith('updated') ? changedFields(e) : [];
        return (
          <li key={i} className="relative">
            <span className="absolute -start-[2.2rem] flex size-6 items-center justify-center rounded-full border bg-background text-muted-foreground">
              <Icon className="size-3.5" />
            </span>
            <p className="text-sm font-medium text-foreground">{label}</p>
            {fields.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Changed: {fields.join(', ')}
              </p>
            )}
            {e.reason && (
              <p className="text-xs text-muted-foreground">
                Reason: {e.reason}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              {e.actor || 'System'} &middot;{' '}
              <time dateTime={e.at}>{new Date(e.at).toLocaleString()}</time>
            </p>
          </li>
        );
      })}
    </ol>
  );
}
