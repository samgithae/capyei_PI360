import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { useNavigate } from 'react-router';
import { api, ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { PageHeader } from '@/components/shared/page-header';
import { Notice } from '@/components/states';
import { ImportStepper, type Batch } from './shared';

interface Summary {
  enrollments: number;
  without_number: number;
  labels: { label: string; filled: number }[];
}

const SKIP = '__skip__'; // Radix Select cannot hold an empty value
const FIELDS = [
  ['placement_status', 'Placement status (required)'],
  ['organisation', 'Organisation'],
  ['address', 'Organisation address'],
  ['designation', 'Designation'],
  ['placement_date', 'Placement date'],
  ['benefits', 'Benefits'],
  ['contact_name', 'Contact person'],
  ['contact_phone', 'Contact phone'],
  ['contact_email', 'Contact email'],
] as const;

/** Stage E: people loaded from a wide sheet keep placement columns as "extra data". Pick which
 * label means what; PI 360 builds a placement import from it, which is then checked, reviewed
 * and loaded exactly like an uploaded placement file (nothing is saved until you approve). */
export function PromoteExtraPage() {
  const nav = useNavigate();
  const [code, setCode] = useState('');
  const [asked, setAsked] = useState('');
  const [mapping, setMapping] = useState<Record<string, string>>({});

  const summary = useQuery({
    queryKey: ['import-extra', asked],
    queryFn: () =>
      api<Summary>(`/imports/extra?programme=${encodeURIComponent(asked)}`),
    enabled: !!asked,
  });

  const promote = useMutation({
    mutationFn: () =>
      post<Batch>('/imports/extra/promote', {
        programme_code: asked,
        columns: Object.fromEntries(
          Object.entries(mapping).filter(([, f]) => f),
        ),
      }),
    onSuccess: (b) => nav(`/imports/${b.id}`),
  });

  const taken = (field: string, label: string) =>
    Object.entries(mapping).some(([l, f]) => f === field && l !== label);
  const hasStatus = Object.values(mapping).includes('placement_status');
  const error = summary.error ?? promote.error;

  return (
    <>
      <Helmet>
        <title>Promote extra data - PI 360</title>
      </Helmet>
      <div className="container-fluid space-y-5">
        <PageHeader
          crumbs={[{ label: 'Create placements from extra data' }]}
          title="Create placements from extra data"
        />
        <ImportStepper current={1} />

        {error && (
          <Notice tone="error" title="This could not be done">
            {error instanceof ApiError
              ? error.message
              : 'Something went wrong.'}
          </Notice>
        )}

        <Card className="max-w-xl">
          <CardContent className="space-y-3">
            <h2 className="font-medium">1. Which programme?</h2>
            <p className="text-sm text-muted-foreground">
              Use this when placement columns were kept as extra data while
              loading people, so the file need not be uploaded again. Type the
              programme code (for example GB).
            </p>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setMapping({});
                setAsked(code.trim().toUpperCase());
              }}
            >
              <Input
                aria-label="Programme code"
                className="w-40"
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
              <Button type="submit" disabled={!code.trim()}>
                Find extra data
              </Button>
            </form>
          </CardContent>
        </Card>

        {summary.data && summary.data.labels.length === 0 && (
          <Notice tone="warning" title="No extra data found">
            {summary.data.enrollments} enrollments in {asked}, none with extra
            data.
          </Notice>
        )}

        {summary.data && summary.data.labels.length > 0 && (
          <>
            <div className="text-sm text-muted-foreground">
              {summary.data.enrollments} enrollments in {asked}
              {summary.data.without_number > 0 &&
                `; ${summary.data.without_number} have no enrollment number and cannot be used`}
              .
            </div>
            <Card>
              <CardContent className="space-y-3">
                <h2 className="font-medium">2. Say what each label means</h2>
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead>Extra label</TableHead>
                      <TableHead>People with a value</TableHead>
                      <TableHead>Means</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.data.labels.map((l) => (
                      <TableRow key={l.label}>
                        <TableCell>{l.label}</TableCell>
                        <TableCell>{l.filled}</TableCell>
                        <TableCell>
                          <Select
                            value={mapping[l.label] || SKIP}
                            onValueChange={(v) =>
                              setMapping((m) => ({
                                ...m,
                                [l.label]: v === SKIP ? '' : v,
                              }))
                            }
                          >
                            <SelectTrigger
                              aria-label={`Meaning of ${l.label}`}
                              className="w-72"
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={SKIP}>
                                Not part of the placement
                              </SelectItem>
                              {FIELDS.map(([f, name]) => (
                                <SelectItem
                                  key={f}
                                  value={f}
                                  disabled={taken(f, l.label)}
                                >
                                  {name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <div className="flex items-center gap-3">
              <Button
                disabled={!hasStatus || promote.isPending}
                onClick={() => promote.mutate()}
              >
                {promote.isPending ? 'Validating...' : 'Validate'}
              </Button>
              <span className="text-xs text-muted-foreground">
                A dry run: it checks every row and changes nothing. Then you
                review employers and statuses, approve and load.
              </span>
            </div>
          </>
        )}
      </div>
    </>
  );
}
