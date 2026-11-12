import { useState, type ReactNode } from 'react';
import { Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTable,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { Input, InputWrapper } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { StatusBadge } from '@/components/shared/status-badge';

// Metronic 9 "table in a card" pattern (as in the demo's user/team tables): a Card with a
// header (title + search/filters), a borderless table region, and a footer with the pager.
// Pages compose these instead of hand-rolling <table> markup, so the look stays consistent.

/** Card shell for a table: title and toolbar in the header, the table as children. */
export function DataCard({
  title,
  description,
  toolbar,
  footer,
  children,
}: {
  title?: string;
  description?: string;
  toolbar?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      {(title || toolbar) && (
        <CardHeader className={title ? 'py-4' : 'justify-start py-4'}>
          <CardHeading>
            {title && <CardTitle>{title}</CardTitle>}
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </CardHeading>
          {toolbar && (
            <CardToolbar className="flex-wrap">{toolbar}</CardToolbar>
          )}
        </CardHeader>
      )}
      <CardTable className="overflow-x-auto">{children}</CardTable>
      {footer && <CardFooter className="justify-between">{footer}</CardFooter>}
    </Card>
  );
}

/** Search box with the magnifier icon the Metronic demo uses. Submits on Enter. */
export function SearchBox({
  placeholder,
  defaultValue,
  onSubmit,
}: {
  placeholder: string;
  defaultValue?: string;
  onSubmit: (value: string) => void;
}) {
  return (
    <InputWrapper className="w-64">
      <Search />
      <Input
        placeholder={placeholder}
        aria-label={placeholder}
        defaultValue={defaultValue}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onSubmit(e.currentTarget.value.trim());
        }}
      />
    </InputWrapper>
  );
}

// Radix Select cannot hold an empty-string value, so "no filter" uses this sentinel.
const ALL = '__all__';

/** Metronic Select used as a filter: the first item clears it. */
export function FilterSelect({
  label,
  value,
  options,
  onChange,
  className = 'w-44',
}: {
  label: string;
  value: string;
  options: { id: string; name: string }[];
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <Select
      value={value || ALL}
      onValueChange={(v) => onChange(v === ALL ? '' : v)}
    >
      <SelectTrigger aria-label={label} className={className}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{label}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.id} value={o.id}>
            {o.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export const PAGE_SIZES = [10, 30, 50, 100];

/** Footer pager: "1-11 of 11", a rows-per-page picker, and Previous/Next. */
export function Pager({
  offset,
  pageSize,
  total,
  onMove,
  onPageSize,
}: {
  offset: number;
  pageSize: number;
  total: number;
  onMove: (to: number) => void;
  onPageSize?: (size: number) => void;
}) {
  const sizes = PAGE_SIZES.includes(pageSize)
    ? PAGE_SIZES
    : [...PAGE_SIZES, pageSize].sort((x, y) => x - y);
  return (
    <>
      <span className="text-sm text-muted-foreground">
        {total === 0 ? 0 : offset + 1}-{Math.min(offset + pageSize, total)} of{' '}
        {total}
      </span>
      <div className="flex items-center gap-3">
        {onPageSize && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            Rows per page
            <select
              aria-label="Rows per page"
              className="h-8 rounded-md border bg-background px-2 text-foreground"
              value={pageSize}
              onChange={(e) => onPageSize(Number(e.target.value))}
            >
              {sizes.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => onMove(offset - pageSize)}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={offset + pageSize >= total}
          onClick={() => onMove(offset + pageSize)}
        >
          Next
        </Button>
      </div>
    </>
  );
}

/** Client-side paging for tables that already hold every row. */
export function useClientPage<T>(rows: T[], initial = 30) {
  const [size, setSize] = useState(initial);
  const [offset, setOffset] = useState(0);
  const last = Math.max(rows.length - 1, 0);
  const start = Math.min(offset, last - (last % size));
  return {
    rows: rows.slice(start, start + size),
    pager:
      rows.length > 0 ? (
        <Pager
          offset={start}
          pageSize={size}
          total={rows.length}
          onMove={(to) => setOffset(Math.max(to, 0))}
          onPageSize={(n) => {
            setSize(n);
            setOffset(0);
          }}
        />
      ) : undefined,
  };
}

/** Kept for existing imports; delegates to the shared StatusBadge so one colour map rules. */
export function ParticipantStatus({ status }: { status: string }) {
  return <StatusBadge status={status} />;
}
