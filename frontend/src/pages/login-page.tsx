import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { TriangleAlert } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Navigate } from 'react-router';
import { ApiError, post } from '@/lib/api';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

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

  const title =
    step === 'credentials'
      ? 'Sign in'
      : step === 'enrol'
        ? 'Set up your authenticator'
        : 'Two-step verification';
  const subtitle =
    step === 'credentials'
      ? 'Use your PI 360 staff account.'
      : step === 'enrol'
        ? 'Add the key below to an authenticator app, then enter the code.'
        : 'Enter the 6-digit code from your authenticator app.';

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <Helmet>
        <title>Sign in | PI 360</title>
      </Helmet>

      {/* Form side: Metronic "branded" sign-in, a card on a muted background */}
      <div className="flex items-center justify-center bg-muted/40 p-6">
        <Card className="w-full max-w-100">
          <CardContent className="p-8">
            <form onSubmit={submit} className="space-y-5" noValidate>
              <div className="space-y-1.5 text-center">
                <div className="mb-3 text-sm font-semibold tracking-wide text-primary">
                  Placement Intelligence 360
                </div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {title}
                </h1>
                <p className="text-sm text-muted-foreground">{subtitle}</p>
              </div>

              {error && (
                <Alert variant="destructive" appearance="light" role="alert">
                  <AlertIcon>
                    <TriangleAlert />
                  </AlertIcon>
                  <AlertTitle>{error}</AlertTitle>
                </Alert>
              )}

              {step === 'credentials' && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <Input
                      id="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      autoComplete="username"
                      autoFocus
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="current-password"
                      required
                    />
                  </div>
                </>
              )}
              {step === 'enrol' && (
                <code className="block break-all rounded-md bg-muted p-3 text-xs">
                  {setupUrl}
                </code>
              )}
              {step !== 'credentials' && (
                <div className="space-y-2">
                  <Label htmlFor="code">Authenticator code</Label>
                  <Input
                    id="code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    autoFocus
                    required
                  />
                </div>
              )}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy
                  ? 'Please wait...'
                  : step === 'credentials'
                    ? 'Continue'
                    : 'Verify'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      {/* Brand side: hidden on small screens, as in the Metronic demo */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-primary p-12 text-primary-foreground lg:flex">
        <div className="absolute -right-24 -top-24 size-96 rounded-full bg-white/10" />
        <div className="absolute -bottom-32 -left-20 size-112 rounded-full bg-white/5" />
        <div className="relative text-lg font-semibold">CAP-YEI</div>
        <div className="relative space-y-4">
          <h2 className="text-3xl font-semibold leading-tight">
            From training to employment,
            <br />
            tracked in one place.
          </h2>
          <p className="max-w-md text-primary-foreground/80">
            Import trainee data, match young people to opportunities and see
            placement outcomes across programmes and counties.
          </p>
        </div>
        <div className="relative text-sm text-primary-foreground/70">
          &copy; {new Date().getFullYear()} CAP-YEI
        </div>
      </div>
    </div>
  );
}
