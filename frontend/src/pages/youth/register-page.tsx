import { FormEvent, useState } from 'react';
import { TriangleAlert } from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { ApiError, post } from '@/lib/api';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AuthShell } from './auth-shell';

/** DRAFT wording: the consent text is not approved yet (D-083). CAP-YEI/DPO must approve it
 * before the sign-up switch is turned on. */
export const CONSENT_TEXT =
  'I agree that CAP-YEI may use these details to set up my PI 360 account and contact me about it.';

/** Public sign-up form (NEW-049). It always ends on the same "check your e-mail" message, so
 * it never reveals whether a person is already known. When sign-up is switched off the server
 * answers 404 and we say so plainly. */
export function RegisterPage() {
  const [f, setF] = useState({
    given_name: '',
    family_name: '',
    date_of_birth: '',
    email: '',
    phone: '',
    programme_code: '',
    enrollment_no: '',
  });
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [off, setOff] = useState(false);
  const [done, setDone] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) =>
    setF((p) => ({ ...p, [k]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!f.given_name || !f.family_name || !f.date_of_birth || !f.email)
      return setError('Fill in your name, date of birth and e-mail.');
    if (!consent) return setError('You need to agree to continue.');
    setBusy(true);
    setError('');
    try {
      await post('/registrations/submit', { ...f, consent });
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setOff(true);
      else
        setError(
          err instanceof ApiError
            ? err.message
            : 'Something went wrong. Try again.',
        );
    } finally {
      setBusy(false);
    }
  };

  const field = (id: keyof typeof f, label: string, type = 'text') => (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} value={f[id]} onChange={set(id)} />
    </div>
  );

  const grid = 'grid gap-3 sm:grid-cols-2';
  return (
    <AuthShell
      title="Create your account"
      subtitle="Tell us a little about you. We will e-mail you a link to confirm your address."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary">
            Sign in
          </Link>
        </>
      }
    >
      <Helmet>
        <title>Create your account | PI 360</title>
      </Helmet>
      {off && (
        <Alert appearance="light" role="status">
          <AlertTitle>
            Sign-up is not open yet. Please ask your CAP-YEI officer.
          </AlertTitle>
        </Alert>
      )}
      {done && (
        <Alert variant="success" appearance="light" role="status">
          <AlertTitle>
            Thank you. If we can use these details, we have sent a link to your
            e-mail. Open it to confirm your address. Check your spam folder if
            it does not arrive.
          </AlertTitle>
        </Alert>
      )}
      {!off && !done && (
        <form onSubmit={submit} className="space-y-4" noValidate>
          <div className={grid}>
            {field('given_name', 'First name')}
            {field('family_name', 'Family name')}
          </div>
          {field('date_of_birth', 'Date of birth', 'date')}
          {field('email', 'E-mail', 'email')}
          {field('phone', 'Phone (optional)', 'tel')}
          <div className={grid}>
            {field('programme_code', 'Programme (optional)')}
            {field('enrollment_no', 'Enrolment number (optional)')}
          </div>
          <label className="flex items-start gap-2 rounded-md bg-muted/50 p-3 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>{CONSENT_TEXT}</span>
          </label>
          {error && (
            <Alert variant="destructive" appearance="light" role="alert">
              <AlertIcon>
                <TriangleAlert />
              </AlertIcon>
              <AlertTitle>{error}</AlertTitle>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? 'Please wait...' : 'Create account'}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
