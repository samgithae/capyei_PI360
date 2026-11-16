import { FormEvent, useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { Helmet } from 'react-helmet-async';
import { toast } from 'sonner';
import { ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DetailList, Section } from '@/components/shared/info-card';
import { PageHeader } from '@/components/shared/page-header';

type Errors = Partial<Record<'current' | 'next' | 'again' | 'form', string>>;

/** Change the signed-in user's own password. Shared by every kind of account (staff, youth and
 * employer), so it lives outside the portals. The server checks the current password and the
 * strength rules; this form only catches the typing slip of a mismatched confirmation. */
export function ChangePasswordForm() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== again) {
      setErrors({ again: 'The two new passwords differ.' });
      return;
    }
    setBusy(true);
    setErrors({});
    try {
      await post('/auth/password/change', {
        current_password: current,
        new_password: next,
      });
      setCurrent('');
      setNext('');
      setAgain('');
      toast.success('Your password has been changed.');
    } catch (err) {
      if (err instanceof ApiError) {
        const wrong = err.fieldMessage('current_password');
        const weak = err.fieldMessage('new_password');
        setErrors(
          wrong || weak
            ? { current: wrong, next: weak }
            : { form: err.message },
        );
      } else {
        setErrors({ form: 'Could not change the password. Try again.' });
      }
    } finally {
      setBusy(false);
    }
  };

  const field = (
    id: string,
    label: string,
    value: string,
    set: (v: string) => void,
    autoComplete: string,
    error?: string,
  ) => (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="password"
        autoComplete={autoComplete}
        value={value}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => set(e.target.value)}
      />
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );

  return (
    <form onSubmit={submit} className="max-w-sm space-y-4">
      {field(
        'pw-current',
        'Current password',
        current,
        setCurrent,
        'current-password',
        errors.current,
      )}
      {field(
        'pw-new',
        'New password',
        next,
        setNext,
        'new-password',
        errors.next,
      )}
      <p className="-mt-2 text-xs text-muted-foreground">
        At least 12 characters. Avoid common passwords and anything like your
        sign-in name.
      </p>
      {field(
        'pw-again',
        'Type the new password again',
        again,
        setAgain,
        'new-password',
        errors.again,
      )}
      {errors.form && (
        <p role="alert" className="text-sm text-destructive">
          {errors.form}
        </p>
      )}
      <Button type="submit" disabled={busy || !current || !next || !again}>
        Change password
      </Button>
    </form>
  );
}

export function AccountPage() {
  const { me } = useAuth();
  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>My account | PI 360</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'My account' }]}
        title="My account"
        description="Who you are signed in as, and your password."
      />
      <Section title="Signed in as">
        <DetailList
          items={[
            { label: 'Sign-in name', value: me?.username },
            {
              label: 'Role',
              value: me?.roles?.length ? me.roles.join(', ') : undefined,
            },
          ]}
        />
      </Section>
      <Section
        title="Change password"
        description="You stay signed in here. Any other device or browser will need the new password."
      >
        <ChangePasswordForm />
      </Section>
    </div>
  );
}
