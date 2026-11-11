import { type ReactNode } from 'react';
import { Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
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

/** Footer pager: "1-11 of 11" on the left, Previous/Next on the right. */
export function Pager({
  offset,
  pageSize,
  total,
  onMove,
}: {
  offset: number;
  pageSize: number;
  total: number;
  onMove: (to: number) => void;
}) {
  return (
    <>
      <span className="text-sm text-muted-foreground">
        {offset + 1}-{Math.min(offset + pageSize, total)} of {total}
      </span>
      <div className="flex gap-2">
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

const PARTICIPANT_TONE: Record<
  string,
  'success' | 'info' | 'warning' | 'secondary'
> = {
  active: 'success',
  completed: 'info',
  withdrawn: 'warning',
  unknown: 'secondary',
  inactive: 'secondary',
  prospect: 'info',
};

/** Participant status as a light Metronic badge with a dot, colour always paired with text. */
export function ParticipantStatus({ status }: { status: string }) {
  return (
    <Badge
      variant={PARTICIPANT_TONE[status] ?? 'secondary'}
      appearance="light"
      className="capitalize"
    >
      {status}
    </Badge>
  );
}
