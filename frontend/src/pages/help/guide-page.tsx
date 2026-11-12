import { useAuth } from '@/auth/auth-context';
import { Forbidden } from '@/auth/guards';
import { Helmet } from 'react-helmet-async';
import { Link, useParams } from 'react-router';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/shared/page-header';
import { ALL_GUIDES } from './all-guides';
import { canSee } from './guides';

/** One guide: numbered steps, a button to the real page, and why it works that way. */
export function GuidePage() {
  const { slug } = useParams();
  const { can } = useAuth();
  const g = ALL_GUIDES.find((x) => x.slug === slug);

  if (!g)
    return (
      <div className="container-fluid py-10 text-center">
        <h1 className="text-xl font-semibold">We could not find that guide</h1>
        <Button asChild className="mt-4">
          <Link to="/help">Back to the Help centre</Link>
        </Button>
      </div>
    );
  if (!canSee(g, can)) return <Forbidden />;

  const related = (g.related ?? [])
    .map((s) => ALL_GUIDES.find((x) => x.slug === s))
    .filter((x): x is NonNullable<typeof x> => !!x && canSee(x, can));

  return (
    <div className="container-fluid max-w-3xl space-y-5">
      <Helmet>
        <title>{g.title}</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Help centre', to: '/help' }, { label: g.title }]}
        title={g.title}
        description={g.summary}
        actions={
          g.to && (
            <Button asChild>
              <Link to={g.to.path}>{g.to.label}</Link>
            </Button>
          )
        }
      />
      <Card>
        <CardContent className="p-5">
          <ol className="list-decimal space-y-2 ps-5 text-sm">
            {g.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </CardContent>
      </Card>
      {g.why && (
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Why: </span>
          {g.why}
        </p>
      )}
      {related.length > 0 && (
        <div className="space-y-1 text-sm">
          <p className="font-medium">Related guides</p>
          <ul className="list-disc ps-5">
            {related.map((r) => (
              <li key={r.slug}>
                <Link className="underline" to={`/help/${r.slug}`}>
                  {r.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Last checked against the system: {g.updated}
      </p>
    </div>
  );
}
