import { Fragment, type ReactNode } from 'react';
import { Link } from 'react-router';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';

export interface Crumb {
  label: string;
  to?: string; // omit on the current page
}

/** Standard page header: breadcrumbs, title (+ badges), a meta line, and the page actions.
 * Every page uses this so titles, spacing and action placement stay the same. */
export function PageHeader({
  crumbs,
  title,
  badges,
  description,
  meta,
  actions,
}: {
  crumbs: Crumb[];
  title: string;
  badges?: ReactNode;
  description?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 pb-2">
      <div className="space-y-2">
        <Breadcrumb>
          <BreadcrumbList>
            {crumbs.map((c, i) => (
              <Fragment key={c.label + i}>
                {i > 0 && <BreadcrumbSeparator />}
                <BreadcrumbItem>
                  {c.to ? (
                    <Link
                      to={c.to}
                      className="hover:text-primary text-muted-foreground"
                    >
                      {c.label}
                    </Link>
                  ) : (
                    <BreadcrumbPage>{c.label}</BreadcrumbPage>
                  )}
                </BreadcrumbItem>
              </Fragment>
            ))}
          </BreadcrumbList>
        </Breadcrumb>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold leading-none text-mono">
            {title}
          </h1>
          {badges}
        </div>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
        {meta && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-secondary-foreground">
            {meta}
          </div>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
