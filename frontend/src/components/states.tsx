import { type ReactNode } from 'react';
import { ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

// Shared data-region states (planning doc 20 §2, NFR-17). Every list or panel that loads
// data shows one of these instead of inventing its own wording. "No access" lives in
// auth/guards.tsx (Forbidden); "Success" is a toast.

export function LoadingState({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed p-8 text-center space-y-2">
      <p className="font-medium">{title}</p>
      {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const message =
    error instanceof ApiError ? error.message : 'Something went wrong.';
  return (
    <div
      role="alert"
      className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 space-y-2"
    >
      <p className="font-medium">We could not load this.</p>
      <p className="text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Inline notice: tone is always paired with text, never colour alone (NFR-02). */
export function Notice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warning' | 'error';
  title: string;
  children?: ReactNode;
}) {
  const style = {
    info: 'border-blue-500/40 bg-blue-500/5',
    warning: 'border-amber-500/50 bg-amber-500/10',
    error: 'border-destructive/40 bg-destructive/5',
  }[tone];
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`rounded-lg border p-3 text-sm ${style}`}
    >
      <p className="font-medium">{title}</p>
      {children && <div className="text-muted-foreground mt-1">{children}</div>}
    </div>
  );
}
