import { ReactNode } from 'react';
import { Card, CardContent } from '@/components/ui/card';

/** Two-column public page shared with sign-in: form card on the left, the CAP-YEI photo panel on
 * the right (on top for small screens). */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="grid min-h-screen w-full lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="order-2 flex min-w-0 flex-col items-center justify-center gap-6 p-8 lg:order-1 lg:p-10">
        <Card className="w-full max-w-md overflow-hidden">
          <div className="flex h-1.5">
            <span className="flex-1 bg-[#fbc30f]" />
            <span className="flex-1 bg-[#da251c]" />
            <span className="flex-1 bg-[#86c127]" />
          </div>
          <CardContent className="space-y-5 p-8">
            <div className="space-y-1.5 text-center">
              <img
                src="/media/app/cap-logo.png"
                alt="CAP Youth Empowerment Institute, Kenya"
                className="mx-auto mb-3 h-16 w-auto rounded-md dark:bg-white dark:p-1.5"
              />
              <div className="text-xs font-semibold uppercase tracking-wide text-primary">
                Placement Intelligence 360
              </div>
              <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
              {subtitle && (
                <p className="text-sm text-muted-foreground">{subtitle}</p>
              )}
            </div>
            {children}
          </CardContent>
        </Card>
        {footer && (
          <p className="text-center text-sm text-muted-foreground">{footer}</p>
        )}
      </div>

      <div className="order-1 flex min-w-0 flex-col overflow-hidden border-border bg-gradient-to-b from-primary/10 via-muted/40 to-background lg:order-2 lg:m-5 lg:h-[calc(100vh-2.5rem)] lg:rounded-xl lg:border">
        <div className="flex flex-col gap-3 p-8 pb-0 lg:p-12 lg:pb-0">
          <h3 className="text-2xl font-semibold text-foreground">
            Linking learning and livelihood
          </h3>
          <div className="max-w-xl text-base font-medium text-secondary-foreground">
            Create your account to see your placement journey, opportunities and
            follow-ups from CAP-YEI in one place.
          </div>
        </div>
        <div className="relative m-12 mb-0 hidden min-h-0 flex-1 overflow-hidden rounded-t-xl border border-b-0 border-border shadow-lg lg:block">
          <img
            src="/media/app/login-photos.webp"
            alt="CAP-YEI trainees at work in practical training"
            className="absolute inset-0 size-full object-cover object-top"
          />
        </div>
      </div>
    </div>
  );
}
