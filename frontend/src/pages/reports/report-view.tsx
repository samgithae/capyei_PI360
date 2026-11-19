import { AlertCircle, Info } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type {
  Chart,
  Report,
  ReportTable,
  Cell as TableCellValue,
  Tile,
} from './report-types';

// One palette for every report so a series keeps its colour from page to page.
const COLORS = [
  '#1b84ff',
  '#17c653',
  '#f6c000',
  '#7239ea',
  '#f1416c',
  '#8c8c9a',
];

export const show = (v: TableCellValue | number | string | null) =>
  v === null || v === undefined || v === '' ? 'n/a' : String(v);

function TileCard({ tile }: { tile: Tile }) {
  return (
    <Card>
      <CardContent className="space-y-1 p-5">
        <div className="text-xs font-medium text-muted-foreground">
          {tile.label}
        </div>
        <div className="text-3xl font-semibold leading-none text-foreground">
          {show(tile.value)}
          {tile.value !== null && tile.unit && (
            <span className="ms-1 text-lg font-medium text-muted-foreground">
              {tile.unit}
            </span>
          )}
        </div>
        {tile.hint && (
          <div className="pt-1 text-xs text-muted-foreground">{tile.hint}</div>
        )}
      </CardContent>
    </Card>
  );
}

/** One chart. The drawing is for the eye; a plain table of the same numbers sits beside it for
 * screen readers, so nothing is only in the picture. */
function ChartCard({ chart }: { chart: Chart }) {
  const empty =
    chart.categories.length === 0 ||
    chart.series.every((s) => s.values.every((v) => !v));
  const config: ChartConfig = Object.fromEntries(
    chart.series.map((s, i) => [
      `s${i}`,
      { label: s.name, color: COLORS[i % COLORS.length] },
    ]),
  );
  const data = chart.categories.map((name, row) => ({
    name,
    ...Object.fromEntries(chart.series.map((s, i) => [`s${i}`, s.values[row]])),
  }));
  const horizontal = chart.type === 'bar';
  const height = horizontal
    ? Math.max(220, 38 * chart.categories.length + 60)
    : 280;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{chart.title}</CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        {empty ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            {chart.empty || 'Nothing to show for these filters.'}
          </p>
        ) : (
          <>
            <ChartContainer
              config={config}
              className="aspect-auto w-full"
              style={{ height }}
            >
              {chart.type === 'pie' ? (
                <PieChart accessibilityLayer={false}>
                  <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                  <Pie
                    rootTabIndex={-1}
                    data={data}
                    dataKey="s0"
                    nameKey="name"
                    innerRadius="50%"
                    outerRadius="85%"
                    paddingAngle={2}
                    strokeWidth={0}
                  >
                    {data.map((d, i) => (
                      <Cell key={d.name} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Legend />
                </PieChart>
              ) : chart.type === 'line' ? (
                <LineChart data={data} accessibilityLayer={false}>
                  <CartesianGrid vertical={false} strokeOpacity={0.2} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  {chart.series.length > 1 && <Legend />}
                  {chart.series.map((s, i) => (
                    <Line
                      key={s.name}
                      dataKey={`s${i}`}
                      name={s.name}
                      stroke={COLORS[i % COLORS.length]}
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  ))}
                </LineChart>
              ) : (
                <BarChart
                  data={data}
                  layout={horizontal ? 'vertical' : 'horizontal'}
                  accessibilityLayer={false}
                >
                  <CartesianGrid
                    vertical={horizontal}
                    horizontal={!horizontal}
                    strokeOpacity={0.2}
                  />
                  {horizontal ? (
                    <>
                      <XAxis
                        type="number"
                        allowDecimals={false}
                        tick={{ fontSize: 11 }}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={130}
                        tick={{ fontSize: 11 }}
                      />
                    </>
                  ) : (
                    <>
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    </>
                  )}
                  <ChartTooltip content={<ChartTooltipContent />} />
                  {chart.series.length > 1 && <Legend />}
                  {chart.series.map((s, i) => (
                    <Bar
                      key={s.name}
                      dataKey={`s${i}`}
                      name={s.name}
                      fill={COLORS[i % COLORS.length]}
                      radius={horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]}
                    />
                  ))}
                </BarChart>
              )}
            </ChartContainer>
            <table className="sr-only">
              <caption>{chart.title}</caption>
              <thead>
                <tr>
                  <th>Group</th>
                  {chart.series.map((s) => (
                    <th key={s.name}>{s.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chart.categories.map((c, row) => (
                  <tr key={c}>
                    <th>{c}</th>
                    {chart.series.map((s) => (
                      <td key={s.name}>{s.values[row]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function DataTable({ table }: { table: ReportTable }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{table.title}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {table.rows.length === 0 ? (
          <p className="p-5 text-sm text-muted-foreground">
            Nothing to list for these filters.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {table.columns.map((c, i) => (
                  <TableHead key={c + i} className={i > 0 ? 'text-end' : ''}>
                    {c}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {table.rows.map((row, r) => (
                <TableRow key={r}>
                  {row.map((cell, i) => (
                    <TableCell
                      key={i}
                      className={i > 0 ? 'text-end tabular-nums' : ''}
                    >
                      {show(cell)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/** A report's body: tiles, charts, tables, then how the numbers are worked out and what is missing. */
export function ReportView({ report }: { report: Report }) {
  return (
    <div className="space-y-5">
      {report.filters_applied.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Showing:</span>
          {report.filters_applied.map((f) => (
            <Badge key={f.key} variant="primary" appearance="light">
              {f.label}: {f.value}
            </Badge>
          ))}
        </div>
      )}

      {report.tiles.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {report.tiles.map((t) => (
            <TileCard key={t.id} tile={t} />
          ))}
        </div>
      )}

      {report.notes.length > 0 && (
        <div
          role="note"
          className="space-y-1 rounded-lg border border-yellow-500/40 bg-yellow-500/5 p-4 text-sm"
        >
          {report.notes.map((n) => (
            <p key={n} className="flex gap-2">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-yellow-600" />
              <span>{n}</span>
            </p>
          ))}
        </div>
      )}

      {report.charts.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {report.charts.map((c) => (
            <ChartCard key={c.id} chart={c} />
          ))}
        </div>
      )}

      {report.tables.map((t) => (
        <DataTable key={t.id} table={t} />
      ))}

      {report.definitions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>How these numbers are worked out</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-muted-foreground">
              The period filters {report.period_on}. Counts follow the records
              you are allowed to see.
            </p>
            <dl className="divide-y">
              {report.definitions.map((d) => (
                <div
                  key={d.name}
                  className="grid gap-1 py-2.5 sm:grid-cols-[14rem_1fr]"
                >
                  <dt className="flex flex-wrap items-center gap-2 font-medium text-foreground">
                    {d.name}
                    {!d.approved && (
                      <Badge variant="warning" appearance="light">
                        Working definition
                      </Badge>
                    )}
                  </dt>
                  <dd className="text-muted-foreground">{d.meaning}</dd>
                </div>
              ))}
            </dl>
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Info className="size-3.5" />
              Generated on {report.generated_on}.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
