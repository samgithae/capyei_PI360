import { useState } from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';

export interface CodeOption {
  code: string;
  name: string;
  programme?: string;
}

/** A searchable drop-down: type part of a code or a name to narrow a long list. The list is
 * filtered by cmdk (the library behind shadcn's Command); we only supply a search string. */
export function CodePicker({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: CodeOption[];
  value: string;
  onChange: (code: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const chosen = options.find((o) => o.code === value);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label={`Default ${label}`}
          className="w-64 justify-between font-normal"
        >
          <span className="truncate">
            {value ? (
              <>
                {value}
                {chosen && (
                  <span className="text-muted-foreground"> {chosen.name}</span>
                )}
              </>
            ) : (
              <span className="text-muted-foreground">Choose {label}...</span>
            )}
          </span>
          <ChevronsUpDown className="size-4 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        <Command>
          <CommandInput placeholder={`Search ${label} code or name...`} />
          <CommandList>
            <CommandEmpty>
              No {label} found. Add it under Reference data first.
            </CommandEmpty>
            <CommandGroup>
              {value && (
                <CommandItem
                  value="__none__ clear no default"
                  onSelect={() => {
                    onChange('');
                    setOpen(false);
                  }}
                >
                  No default
                </CommandItem>
              )}
              {options.map((o) => (
                <CommandItem
                  key={`${o.programme ?? ''}/${o.code}`}
                  value={`${o.code} ${o.name}`}
                  onSelect={() => {
                    onChange(o.code);
                    setOpen(false);
                  }}
                >
                  <Check
                    className={o.code === value ? 'size-4' : 'size-4 opacity-0'}
                  />
                  <span className="font-medium">{o.code}</span>
                  <span className="truncate text-muted-foreground">
                    {o.name}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
