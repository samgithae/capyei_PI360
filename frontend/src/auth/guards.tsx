import { Navigate, Outlet } from 'react-router';
import { ScreenLoader } from '@/components/screen-loader';
import { useAuth } from './auth-context';

/** Everything inside needs a signed-in user; others go to the sign-in page. */
export function RequireAuth() {
  const { loading, authenticated } = useAuth();
  if (loading) return <ScreenLoader />;
  return authenticated ? <Outlet /> : <Navigate to="/login" replace />;
}

/** The server still enforces every permission; this only avoids showing dead ends. */
export function RequirePermission({ permission }: { permission: string }) {
  const { can } = useAuth();
  return can(permission) ? <Outlet /> : <Forbidden />;
}

export function Forbidden() {
  return (
    <div className="container-fluid py-10 text-center">
      <h1 className="text-xl font-semibold">
        You do not have access to this page
      </h1>
      <p className="text-muted-foreground mt-2">
        Ask an administrator if you think you should.
      </p>
    </div>
  );
}
