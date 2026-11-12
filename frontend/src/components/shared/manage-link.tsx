import { useAuth } from '@/auth/auth-context';
import { Link } from 'react-router';

/** "X missing? Add or manage X" shortcut for people allowed to edit reference data. */
export function ManageLink({
  missing,
  to,
  label,
}: {
  missing: string;
  to: string;
  label: string;
}) {
  const { can } = useAuth();
  if (!can('reference.manage')) return null;
  return (
    <p className="text-xs text-muted-foreground">
      {missing} missing?{' '}
      <Link to={to} className="text-primary underline" target="_blank">
        {label}
      </Link>{' '}
      (opens in a new tab, then reopen this form).
    </p>
  );
}
