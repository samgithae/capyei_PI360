import { useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';

// "None chosen" uses this sentinel so it can sit in the list like any option.
const NONE = '__none__';
// Short lists (gender, status) need no search box; long ones (counties, courses) do.
const SEARCH_FROM = 6;

/** Searchable select with plain string in/out; `emptyLabel` adds a "none" option that maps to ''. */
export function SelectField({
  label,
  value,
  options,
  onChange,
  emptyLabel,
  className,
}: {
  label: string;
  value: string;
  options: { id: string; name: string }[];
  onChange: (value: string) => void;
  emptyLabel?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const chosen = options.find((o) => o.id === value);
  const items = [
    ...(emptyLabel ? [{ id: NONE, name: emptyLabel }] : []),
    ...options,
  ];
  const shown = chosen?.name ?? (value ? '' : emptyLabel) ?? '';

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          className={cn('justify-between font-normal', className)}
        >
          <span className={cn('truncate', !shown && 'text-muted-foreground')}>
            {shown || label}
          </span>
          <ChevronDown className="size-4 shrink-0 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-(--radix-popover-trigger-width) min-w-56 p-0"
      >
        <Command
          filter={(itemValue, search) =>
            itemValue
              .split('|')[0]
              .toLowerCase()
              .includes(search.trim().toLowerCase())
              ? 1
              : 0
          }
        >
          {items.length > SEARCH_FROM && (
            <CommandInput placeholder={`Search ${label.toLowerCase()}…`} />
          )}
          <CommandList>
            <CommandEmpty>Nothing found.</CommandEmpty>
            {items.map((o) => (
              <CommandItem
                key={o.id}
                value={`${o.name}|${o.id}`}
                onSelect={() => {
                  onChange(o.id === NONE ? '' : o.id);
                  setOpen(false);
                }}
              >
                <span className="truncate">{o.name}</span>
                {(o.id === value || (o.id === NONE && !value)) && (
                  <Check className="ms-auto size-4 text-primary" />
                )}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
