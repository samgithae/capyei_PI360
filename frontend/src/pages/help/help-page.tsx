import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/shared/page-header';
import { ALL_GUIDES } from './all-guides';
import { GROUPS, guidesFor, matches } from './guides';

/** Help centre home: the reader's "start here" guide, then task guides they are allowed to use. */
export function HelpPage() {
  const { can } = useAuth();
  const [q, setQ] = useState('');
  const { start, rest } = guidesFor(ALL_GUIDES, can);
  const shown = rest.filter((g) => matches(g, q));

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>Help centre</title>
      </Helmet>
      <PageHeader
        crumbs={[{ label: 'Help centre' }]}
        title="Help centre"
        description="Short guides to the things you can do here."
      />
      {start && !q && (
        <Card>
          <CardContent className="space-y-2 p-5">
            <p className="text-xs font-medium uppercase text-muted-foreground">
              Start here
            </p>
            <Link
              to={`/help/${start.slug}`}
              className="text-lg font-semibold hover:underline"
            >
              {start.title}
            </Link>
            <p className="text-sm text-muted-foreground">{start.summary}</p>
          </CardContent>
        </Card>
      )}
      <Input
        aria-label="Search the guides"
        placeholder="Search the guides"
        className="max-w-sm"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {GROUPS.map((group) => {
        const items = shown.filter((g) => g.group === group);
        if (items.length === 0) return null;
        return (
          <section key={group} className="space-y-2">
            <h2 className="text-sm font-semibold">{group}</h2>
            <ul className="grid gap-3 md:grid-cols-2">
              {items.map((g) => (
                <li key={g.slug}>
                  <Link to={`/help/${g.slug}`} className="block h-full">
                    <Card className="h-full transition-colors hover:bg-muted/40">
                      <CardContent className="space-y-1 p-4">
                        <p className="font-medium">{g.title}</p>
                        <p className="text-sm text-muted-foreground">
                          {g.summary}
                        </p>
                      </CardContent>
                    </Card>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      {shown.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {q ? 'No guide matches your search.' : 'No guides for your role yet.'}
        </p>
      )}
    </div>
  );
}
