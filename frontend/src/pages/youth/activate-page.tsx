import { FormEvent, useEffect, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type Phase = 'checking' | 'ready' | 'invalid' | 'done';

/** Public page opened from the invite e-mail. The one-time token is in the URL fragment so it
 * is never sent to a server log; the youth chooses a password, then signs in as usual. */
export function ActivatePage() {
  const [token] = useState(() =>
    new URLSearchParams(window.location.hash.replace(/^#/, '')).get('token'),
  );
  const [phase, setPhase] = useState<Phase>(token ? 'checking' : 'invalid');
  const [message, setMessage] = useState(
    token ? '' : 'This link is not complete. Ask your officer for a new one.',
  );
  const [password, setPassword] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    post('/youth/activate/check', { token })
      .then(() => setPhase('ready'))
      .catch((e) => {
        setMessage(e instanceof ApiError ? e.message : 'Could not check link.');
        setPhase('invalid');
      });
    // Drop the token from the address bar and history once read.
    window.history.replaceState(null, '', window.location.pathname);
  }, [token]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== again) return setMessage('The two passwords differ.');
    setBusy(true);
    setMessage('');
    try {
      await post('/youth/activate', { token, password });
      setPhase('done');
    } catch (err) {
      setMessage(
        err instanceof ApiError ? err.message : 'Could not set the password.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Helmet>
        <title>Activate your account</title>
      </Helmet>
      <Card className="w-full max-w-sm">
        <CardContent className="space-y-4 p-6">
          <h1 className="text-lg font-semibold">Activate your account</h1>
          {phase === 'checking' && <p role="status">Checking your link...</p>}
          {phase === 'invalid' && (
            <p role="alert" className="text-destructive text-sm">
              {message}
            </p>
          )}
          {phase === 'done' && (
            <>
              <p role="status" className="text-sm">
                Your password is set. You can sign in now. Your sign-in name is
                the e-mail address the invite was sent to.
              </p>
              <Button asChild>
                <Link to="/login">Go to sign in</Link>
              </Button>
            </>
          )}
          {phase === 'ready' && (
            <form onSubmit={submit} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="pw">Choose a password</Label>
                <Input
                  id="pw"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pw2">Type it again</Label>
                <Input
                  id="pw2"
                  type="password"
                  autoComplete="new-password"
                  value={again}
                  onChange={(e) => setAgain(e.target.value)}
                />
              </div>
              {message && (
                <p role="alert" className="text-destructive text-sm">
                  {message}
                </p>
              )}
              <Button type="submit" disabled={busy || !password}>
                Set password
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
