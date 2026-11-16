import { useState, type ReactNode } from 'react';
import { useAuth } from '@/auth/auth-context';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  BadgeCheck,
  Briefcase,
  CalendarClock,
  Send,
  Users,
  UserX,
} from 'lucide-react';
import { Helmet } from 'react-helmet-async';
import { Link } from 'react-router';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from 'recharts';
import { api, type Health } from '@/lib/api';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { Progress } from '@/components/ui/progress';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { DataCard, FilterSelect } from '@/components/data-card';
import { PageHeader } from '@/components/shared/page-header';
import { ErrorState } from '@/components/states';
import {
  listUrl,
  PERIODS,
  type Dashboard,
  type RecentRow,
} from './dashboard/dashboard-types';

type Tone = 'primary' | 'success' | 'info' | 'warning' | 'destructive';

const TONE: Record<Tone, { soft: string; text: string; bar: string }> = {
  primary: { soft: 'bg-primary/10', text: 'text-primary', bar: 'bg-primary' },
  success: {
    soft: 'bg-green-500/10',
    text: 'text-green-600',
    bar: 'bg-green-500',
  },
  info: {
    soft: 'bg-violet-500/10',
    text: 'text-violet-600',
    bar: 'bg-violet-500',
  },
  warning: {
    soft: 'bg-yellow-500/10',
    text: 'text-yellow-600',
    bar: 'bg-yellow-500',
  },
  destructive: {
    soft: 'bg-destructive/10',
    text: 'text-destructive',
    bar: 'bg-destructive',
  },
};

const pct = (v: number | null) => (v === null ? 'n/a' : `${v}%`);

/** A KPI card: icon, animated number, label, and an optional progress meter. */
function Stat({
  icon,
  tone,
  label,
  value,
  note,
  meter,
  to,
}: {
  icon: ReactNode;
  tone: Tone;
  label: string;
  value: number;
  note?: string;
  meter?: number | null;
  to: string;
}) {
  const c = TONE[tone];
  return (
    <Link to={to} className="block">
      <Card className="h-full transition-shadow hover:shadow-md">
        <CardContent className="space-y-4 p-5">
          <div className="flex items-start justify-between">
            <div
              className={`flex size-11 items-center justify-center rounded-full ${c.soft} ${c.text}`}
            >
              {icon}
            </div>
            <span className="text-xs font-medium text-muted-foreground">
              {label}
            </span>
          </div>
          <div>
            <div className="text-3xl font-semibold leading-none text-foreground">
              {value}
            </div>
            {note && (
              <div className="mt-2 text-sm text-muted-foreground">{note}</div>
            )}
          </div>
          {meter !== undefined && (
            <Progress
              value={Math.min(100, meter ?? 0)}
              className="h-1.5"
              indicatorClassName={c.bar}
            />
          )}
        </CardContent>
      </Card>
    </Link>
  );
}

/** Rows with a meter; the count is a link to the records it counts. */
function Bars({
  rows,
  period,
  tone = 'primary',
}: {
  rows: { label: string; key: string; count: number }[];
  period: string;
  tone?: Tone;
}) {
  const top = Math.max(1, ...rows.map((r) => r.count));
  return (
    <ul className="space-y-4 p-5">
      {rows.map((r) => (
        <li key={r.key} className="text-sm">
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <span className="text-muted-foreground">{r.label}</span>
            <Link
              className="font-semibold text-foreground hover:text-primary hover:underline"
              to={listUrl(r.key, r.label, period)}
            >
              {r.count}
            </Link>
          </div>
          <Progress
            value={(100 * r.count) / top}
            className="h-2"
            indicatorClassName={TONE[tone].bar}
          />
        </li>
      ))}
    </ul>
  );
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('');

/** A short feed of the newest records, each linking to the record. */
function Recent({ rows, empty }: { rows: RecentRow[]; empty: string }) {
  if (rows.length === 0)
    return <p className="p-5 text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y">
      {rows.map((r) => (
        <li key={r.id} className="flex items-center gap-3 px-5 py-3">
          <Avatar className="size-9">
            <AvatarFallback className="bg-primary/10 text-xs font-medium text-primary">
              {initials(r.name)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <Link
              to={r.link}
              className="block truncate text-sm font-medium text-foreground hover:text-primary"
            >
              {r.name}
            </Link>
            <div className="truncate text-xs text-muted-foreground">
              {r.detail}
            </div>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">
            {new Date(r.on).toLocaleDateString()}
          </span>
        </li>
      ))}
    </ul>
  );
}

const ALERT_ICON: Record<string, { icon: ReactNode; tone: Tone }> = {
  'referrals.overdue': {
    icon: <AlertTriangle className="size-5" />,
    tone: 'destructive',
  },
  'opportunities.closing_soon': {
    icon: <CalendarClock className="size-5" />,
    tone: 'warning',
  },
  'opportunities.unreferred': {
    icon: <Briefcase className="size-5" />,
    tone: 'info',
  },
  'youth.not_referred': {
    icon: <UserX className="size-5" />,
    tone: 'primary',
  },
};

const GENDER_COLORS = ['#1b84ff', '#f1416c', '#7239ea', '#8c8c9a'];

/** Programme dashboard (T-070). Every number comes from one endpoint and links to the list of
 * records it counts; sections the user may not open are left out by the API. */
export function OverviewPage() {
  const { can } = useAuth();
  const seeImports = can('imports.run');
  const [period, setPeriod] = useState('90');

  const dash = useQuery({
    queryKey: ['dashboard', period],
    queryFn: () => api<Dashboard>(`/reporting/dashboard?period=${period}`),
  });
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health'),
    retry: false,
  });

  const d = dash.data;
  const t = d?.tiles;
  const go = (key: string, title: string) => listUrl(key, title, period);

  const genderTotal = d?.gender.reduce((n, g) => n + g.count, 0) ?? 0;
  const genderConfig: ChartConfig = Object.fromEntries(
    (d?.gender ?? []).map((g, i) => [
      g.label,
      { label: g.label, color: GENDER_COLORS[i % GENDER_COLORS.length] },
    ]),
  );
  const trendConfig: ChartConfig = {
    referred: { label: 'Referred', color: '#1b84ff' },
    placed: { label: 'Placed', color: '#17c653' },
  };

  return (
    <>
      <Helmet>
        <title>Dashboard | PI 360</title>
      </Helmet>
      <div className="container-fluid space-y-5">
        <PageHeader
          crumbs={[{ label: 'Dashboard' }]}
          title="Programme dashboard"
          description="Are young people moving from registration and training into work, and where are we losing them? Click any number to see the records."
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <FilterSelect
                label="Period"
                value={period}
                options={PERIODS}
                onChange={setPeriod}
              />
              <Badge
                variant={
                  health.isError
                    ? 'destructive'
                    : health.data
                      ? 'success'
                      : 'secondary'
                }
                appearance="light"
              >
                {health.isError
                  ? 'API unreachable'
                  : health.data
                    ? `API ${health.data.status} · v${health.data.version}`
                    : 'Checking API'}
              </Badge>
              {seeImports && (
                <Button asChild size="sm">
                  <Link to="/imports/new">New import</Link>
                </Button>
              )}
            </div>
          }
        />

        {dash.isError && (
          <ErrorState error={dash.error} onRetry={() => void dash.refetch()} />
        )}

        {d && t && (
          <>
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
              {d.can.youth && (
                <Stat
                  icon={<Users className="size-5" />}
                  tone="primary"
                  label="Registered youth"
                  value={t.registered}
                  note={`${t.referred} referred so far`}
                  meter={t.registered ? (100 * t.referred) / t.registered : 0}
                  to={go('youth.registered', 'Registered youth')}
                />
              )}
              {d.can.youth && (
                <Stat
                  icon={<BadgeCheck className="size-5" />}
                  tone="success"
                  label="Placed"
                  value={t.placed}
                  note={`Placement rate ${pct(t.placement_rate)}`}
                  meter={t.placement_rate}
                  to={go('youth.placed', 'Placed youth')}
                />
              )}
              {d.can.referrals && (
                <Stat
                  icon={<Send className="size-5" />}
                  tone="info"
                  label="Referrals submitted"
                  value={t.submitted}
                  note={`Conversion to placement ${pct(t.conversion)}`}
                  meter={t.conversion}
                  to={go('referrals.submitted', 'Referrals submitted')}
                />
              )}
              {d.can.employers && (
                <Stat
                  icon={<Briefcase className="size-5" />}
                  tone="warning"
                  label="Open opportunities"
                  value={t.open_opportunities}
                  note={`${t.active_employers} active employers`}
                  to={go('opportunities.open', 'Open opportunities')}
                />
              )}
            </div>

            {d.alerts.length > 0 && (
              <div>
                <h3 className="mb-3 text-sm font-semibold text-foreground">
                  Needs attention
                </h3>
                <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
                  {d.alerts.map((a) => {
                    const v = ALERT_ICON[a.key] ?? {
                      icon: <AlertTriangle className="size-5" />,
                      tone: 'warning' as Tone,
                    };
                    return (
                      <Link
                        key={a.key}
                        to={go(a.key, a.label)}
                        className="block"
                      >
                        <Card className="h-full transition-shadow hover:shadow-md">
                          <CardContent className="flex items-center gap-4 p-5">
                            <div
                              className={`flex size-11 shrink-0 items-center justify-center rounded-full ${TONE[v.tone].soft} ${TONE[v.tone].text}`}
                            >
                              {v.icon}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-sm font-medium text-foreground">
                                {a.label}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {a.hint}
                              </div>
                            </div>
                            <Badge
                              variant={v.tone}
                              appearance="light"
                              className="px-2.5 text-base font-semibold"
                            >
                              {a.count}
                            </Badge>
                          </CardContent>
                        </Card>
                      </Link>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="grid gap-5 lg:grid-cols-3">
              {d.can.youth && (
                <DataCard
                  title="From registration to placement"
                  description={
                    t.median_days_to_placement !== null
                      ? `Median ${t.median_days_to_placement} days from referral to placement`
                      : undefined
                  }
                >
                  <Bars rows={d.funnel} period={period} tone="success" />
                </DataCard>
              )}
              {d.can.youth && d.gender.length > 0 && (
                <DataCard
                  title="Gender and placement"
                  description="Registered youth by gender"
                >
                  <div className="p-5">
                    <ChartContainer
                      config={genderConfig}
                      className="mx-auto aspect-square h-52"
                    >
                      <PieChart>
                        <ChartTooltip
                          content={<ChartTooltipContent hideLabel />}
                        />
                        <Pie
                          data={d.gender}
                          dataKey="count"
                          nameKey="label"
                          innerRadius="60%"
                          outerRadius="90%"
                          paddingAngle={2}
                          strokeWidth={0}
                        >
                          {d.gender.map((g, i) => (
                            <Cell
                              key={g.key}
                              fill={GENDER_COLORS[i % GENDER_COLORS.length]}
                            />
                          ))}
                        </Pie>
                      </PieChart>
                    </ChartContainer>
                    <div className="-mt-1 text-center text-xs text-muted-foreground">
                      {genderTotal} youth in total
                    </div>
                    <ul className="mt-4 divide-y text-sm">
                      {d.gender.map((g, i) => (
                        <li
                          key={g.key}
                          className="flex items-center justify-between gap-3 py-2.5"
                        >
                          <span className="flex items-center gap-2">
                            <span
                              className="size-2.5 rounded-full"
                              style={{
                                background:
                                  GENDER_COLORS[i % GENDER_COLORS.length],
                              }}
                            />
                            <Link
                              className="font-medium text-foreground hover:text-primary hover:underline"
                              to={go(g.key, `${g.label} youth`)}
                            >
                              {g.label} · {g.count}
                            </Link>
                          </span>
                          <Link
                            className="text-muted-foreground hover:text-primary hover:underline"
                            to={go(g.placed_key, `${g.label} youth placed`)}
                          >
                            {g.placed} placed ({pct(g.rate)})
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                </DataCard>
              )}
              {d.can.referrals && (
                <DataCard
                  title="Referral pipeline"
                  description="Where referrals are now"
                >
                  <Bars rows={d.pipeline} period={period} tone="info" />
                </DataCard>
              )}
            </div>

            {d.can.referrals && (
              <DataCard
                title="Referred and placed, by month"
                description="Last 12 months. Placements are from referrals reaching Placed and placement records."
              >
                <ChartContainer
                  config={trendConfig}
                  className="aspect-auto h-64 w-full p-4"
                >
                  <BarChart data={d.trend}>
                    <CartesianGrid vertical={false} strokeOpacity={0.2} />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Legend />
                    <Bar
                      dataKey="referred"
                      name="Referred"
                      fill="var(--color-referred)"
                      radius={[3, 3, 0, 0]}
                    />
                    <Bar
                      dataKey="placed"
                      name="Placed"
                      fill="var(--color-placed)"
                      radius={[3, 3, 0, 0]}
                    />
                  </BarChart>
                </ChartContainer>
              </DataCard>
            )}

            <div className="grid gap-5 lg:grid-cols-2">
              {d.can.employers && (
                <DataCard
                  title="Recent opportunities"
                  toolbar={
                    <Button asChild variant="outline" size="sm">
                      <Link to="/opportunities">View all</Link>
                    </Button>
                  }
                >
                  <Recent
                    rows={d.recent.opportunities}
                    empty="No opportunities yet."
                  />
                </DataCard>
              )}
              {d.can.referrals && (
                <DataCard
                  title="Recent referrals"
                  toolbar={
                    <Button asChild variant="outline" size="sm">
                      <Link to="/referrals">View all</Link>
                    </Button>
                  }
                >
                  <Recent rows={d.recent.referrals} empty="No referrals yet." />
                </DataCard>
              )}
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              {d.can.youth && d.age.length > 0 && (
                <DataCard title="Age of registered youth">
                  <Bars rows={d.age} period={period} />
                </DataCard>
              )}
              {d.can.youth && d.counties.length > 0 && (
                <DataCard
                  title="By county"
                  description="Registered youth, placements, and employers in the same county"
                >
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/40">
                        <TableHead>County</TableHead>
                        <TableHead>Youth</TableHead>
                        <TableHead>Placed</TableHead>
                        <TableHead>Employers</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {d.counties.map((c) => (
                        <TableRow key={c.key}>
                          <TableCell>{c.name}</TableCell>
                          <TableCell>
                            <Link
                              className="text-primary hover:underline"
                              to={go(
                                `youth.county.${c.key}`,
                                `Youth in ${c.name}`,
                              )}
                            >
                              {c.registered}
                            </Link>
                          </TableCell>
                          <TableCell>
                            <Link
                              className="text-primary hover:underline"
                              to={go(
                                `youth.placed.county.${c.key}`,
                                `Placed in ${c.name}`,
                              )}
                            >
                              {c.placed}
                            </Link>{' '}
                            <span className="text-muted-foreground">
                              ({pct(c.rate)})
                            </span>
                          </TableCell>
                          <TableCell>{c.employers}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </DataCard>
              )}
            </div>

            <p className="text-xs text-muted-foreground">
              Not shown because PI 360 does not hold the data yet:{' '}
              {d.not_captured.join('; ')}.
            </p>
          </>
        )}
      </div>
    </>
  );
}
