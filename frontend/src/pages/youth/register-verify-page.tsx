import { useEffect, useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { ApiError, post } from '@/lib/api';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { AuthShell } from './auth-shell';

type Phase = 'checking' | 'done' | 'invalid';

/** Landing page for the e-mail link. The one-time token is in the URL fragment (never sent to
 * a server log); we confirm it once and remove it from the address bar. */
export function RegisterVerifyPage() {
  const [token] = useState(() =>
    new URLSearchParams(window.location.hash.replace(/^#/, '')).get('token'),
  );
  const [phase, setPhase] = useState<Phase>(token ? 'checking' : 'invalid');
  const [message, setMessage] = useState(
    token ? '' : 'This link is not complete. Please sign up again.',
  );

  useEffect(() => {
    if (!token) return;
    post('/registrations/verify', { token })
      .then(() => setPhase('done'))
      .catch((e) => {
        setMessage(e instanceof ApiError ? e.message : 'Could not check link.');
        setPhase('invalid');
      });
    window.history.replaceState(null, '', window.location.pathname);
  }, [token]);

  return (
    <AuthShell title="Confirm your e-mail">
      <Helmet>
        <title>Confirm your e-mail | PI 360</title>
      </Helmet>
      {phase === 'checking' && (
        <p role="status" className="text-center text-sm">
          Checking your link...
        </p>
      )}
      {phase === 'done' && (
        <Alert variant="success" appearance="light" role="status">
          <AlertTitle>
            Thank you, your e-mail is confirmed. A CAP-YEI officer will check
            your details and be in touch.
          </AlertTitle>
        </Alert>
      )}
      {phase === 'invalid' && (
        <Alert variant="destructive" appearance="light" role="alert">
          <AlertTitle>{message}</AlertTitle>
        </Alert>
      )}
    </AuthShell>
  );
}
