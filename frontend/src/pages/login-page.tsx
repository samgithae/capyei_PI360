import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { Helmet } from 'react-helmet-async';
import { Navigate } from 'react-router';
import { ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type Step = 'credentials' | 'verify' | 'enrol';

/** Sign in: password, then the authenticator code. First-time users enrol an authenticator. */
export function LoginPage() {
  const { authenticated, login, verifyMfa, refresh } = useAuth();
  const [step, setStep] = useState<Step>('credentials');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [setupUrl, setSetupUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (authenticated) return <Navigate to="/" replace />;

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : 'Something went wrong. Try again.',
      );
    } finally {
      setBusy(false);
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      if (step === 'credentials') {
        const r = await login(username, password);
        if (r.status === 'mfa_required') {
          if (r.mfa_enrolled) {
            setStep('verify');
          } else {
            const s = await post<{ config_url: string }>('/auth/mfa/setup');
            setSetupUrl(s.config_url);
            setStep('enrol');
          }
        }
      } else if (step === 'verify') {
        await verifyMfa(code);
      } else {
        await post('/auth/mfa/confirm', { code });
        await refresh();
      }
      setPassword('');
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <Helmet>
        <title>Sign in | PI 360</title>
      </Helmet>
      <form onSubmit={submit} className="w-full max-w-sm space-y-4" noValidate>
        <h1 className="text-2xl font-semibold">Sign in to PI 360</h1>
        {step === 'credentials' && (
          <>
            <label className="block space-y-1 text-sm">
              <span>Username</span>
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span>Password</span>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
          </>
        )}
        {step === 'enrol' && (
          <div className="text-sm space-y-2">
            <p>
              Set up an authenticator app. Add this key to it, then enter the
              6-digit code.
            </p>
            <code className="block break-all rounded bg-muted p-2 text-xs">
              {setupUrl}
            </code>
          </div>
        )}
        {step !== 'credentials' && (
          <label className="block space-y-1 text-sm">
            <span>Authenticator code</span>
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              autoFocus
              required
            />
          </label>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={busy}>
          {step === 'credentials' ? 'Continue' : 'Verify'}
        </Button>
      </form>
    </div>
  );
}
