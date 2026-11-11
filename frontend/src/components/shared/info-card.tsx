import { type ReactNode } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';

/** A titled card with an optional header action; children go in the body. */
export function Section({
  title,
  description,
  action,
  children,
  flush = false,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  flush?: boolean; // true: no body padding (for tables)
}) {
  return (
    <Card>
      <CardHeader className="py-4">
        <CardHeading>
          <CardTitle>{title}</CardTitle>
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </CardHeading>
        {action && <CardToolbar>{action}</CardToolbar>}
      </CardHeader>
      {flush ? children : <CardContent>{children}</CardContent>}
    </Card>
  );
}

/** Label/value list for a record's attributes. Empty values show a dash, so gaps are visible. */
export function DetailList({
  items,
}: {
  items: { label: string; value?: ReactNode }[];
}) {
  return (
    <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
      {items.map((i) => (
        <div key={i.label} className="space-y-1">
          <dt className="text-xs font-medium uppercase text-muted-foreground">
            {i.label}
          </dt>
          <dd className="text-sm text-foreground break-words">
            {i.value || <span className="text-muted-foreground">-</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** One headline number with a label (summary row above a table). Pass real counts only. */
export function SummaryStatCard({
  label,
  value,
  loading,
}: {
  label: string;
  value?: number;
  loading?: boolean;
}) {
  return (
    <Card>
      <CardContent className="space-y-1 p-5">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold text-mono">
          {loading || value === undefined ? '...' : value}
        </p>
      </CardContent>
    </Card>
  );
}
