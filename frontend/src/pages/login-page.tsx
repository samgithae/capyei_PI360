import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { Eye, EyeOff, TriangleAlert } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Navigate } from 'react-router';
import { ApiError, post } from '@/lib/api';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input, InputWrapper } from '@/components/ui/input';
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
  const [showPassword, setShowPassword] = useState(false);

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

      {/* Form side (Metronic auth/signin: card centred in its half) */}
      <div className="order-2 flex items-center justify-center p-8 lg:order-1 lg:p-10">
        <Card className="w-full max-w-100">
          <CardContent className="p-6">
            <form onSubmit={submit} className="space-y-5" noValidate>
              <div className="space-y-1.5 text-center">
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
                    <InputWrapper>
                      <Input
                        id="password"
                        type={showPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete="current-password"
                        required
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        mode="icon"
                        size="sm"
                        className="-me-1.5 size-7"
                        aria-label={
                          showPassword ? 'Hide password' : 'Show password'
                        }
                        onClick={() => setShowPassword((v) => !v)}
                      >
                        {showPassword ? <EyeOff /> : <Eye />}
                      </Button>
                    </InputWrapper>
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

      {/* Branded panel (Metronic: rounded, bordered, inset on desktop) */}
      <div className="order-1 flex flex-col overflow-hidden border-border bg-gradient-to-b from-primary/10 via-muted/40 to-background lg:order-2 lg:m-5 lg:rounded-xl lg:border">
        <div className="flex flex-col gap-4 p-8 lg:p-12">
          <img
            src="/media/app/cap-logo.png"
            alt="CAP Youth Empowerment Institute, Kenya"
            className="h-20 w-fit max-w-none"
          />
          <div className="flex h-1.5 w-20 overflow-hidden rounded-full">
            <span className="flex-1 bg-[#fbc30f]" />
            <span className="flex-1 bg-[#da251c]" />
            <span className="flex-1 bg-[#86c127]" />
          </div>
          <div className="flex flex-col gap-3">
            <h2 className="text-2xl font-semibold">
              Placement Intelligence 360
            </h2>
            <p className="text-base font-medium text-secondary-foreground">
              Linking learning and livelihood,{' '}
              <span className="font-semibold text-foreground">
                tracked in one place
              </span>
              . Import trainee data, match young people to opportunities and see
              outcomes across programmes and counties.
            </p>
          </div>
        </div>
        {/* Photo card, cropped at the bottom like the template's app preview */}
        <div className="mt-auto hidden px-12 lg:block">
          <img
            src="/media/app/login-hero.webp"
            alt=""
            className="h-72 w-full rounded-t-xl border border-b-0 border-border object-cover object-top shadow-lg"
          />
        </div>
      </div>
    </div>
  );
}
