import { useCallback, useState, type ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Archive,
  ArchiveRestore,
  Eye,
  MoreHorizontal,
  Pencil,
} from 'lucide-react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { TableHead } from '@/components/ui/table';
import { ConfirmDialog } from '@/components/shared/modals';

// Reusable pieces for list pages: a checkbox column with select-all, a row action menu
// (View / Edit / Archive), a bulk toolbar, and the archive/restore flow with its confirmation.
// "Archive" is a soft delete: hidden from lists but kept, and an administrator can restore it.

const NONE: ReadonlySet<string> = new Set();

/** Row selection for one page of a list. Resets when `resetKey` (page, filters) changes. */
export function useSelection(ids: string[], resetKey: string) {
  const [state, setState] = useState<{ key: string; ids: ReadonlySet<string> }>(
    {
      key: resetKey,
      ids: NONE,
    },
  );
  const current = state.key === resetKey ? state.ids : NONE;
  const selected = ids.filter((id) => current.has(id));
  const set = useCallback(
    (next: Iterable<string>) => setState({ key: resetKey, ids: new Set(next) }),
    [resetKey],
  );
  return {
    selected,
    isSelected: (id: string) => current.has(id),
    toggle: (id: string) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      set(next);
    },
    allSelected: ids.length > 0 && selected.length === ids.length,
    someSelected: selected.length > 0 && selected.length < ids.length,
    toggleAll: () => set(selected.length === ids.length ? [] : ids),
    clear: () => set([]),
  };
}

type Selection = ReturnType<typeof useSelection>;

/** Header cell with the select-all checkbox (indeterminate when some rows are chosen). */
export function SelectAllHead({ selection }: { selection: Selection }) {
  return (
    <TableHead className="w-10">
      <Checkbox
        aria-label="Select all rows on this page"
        checked={
          selection.allSelected
            ? true
            : selection.someSelected
              ? 'indeterminate'
              : false
        }
        onCheckedChange={selection.toggleAll}
      />
    </TableHead>
  );
}

/** Checkbox for one row. `label` names the row for screen readers, e.g. "Select Jane Doe". */
export function RowCheckbox({
  selection,
  id,
  label,
}: {
  selection: Selection;
  id: string;
  label: string;
}) {
  return (
    <Checkbox
      aria-label={label}
      checked={selection.isSelected(id)}
      onCheckedChange={() => selection.toggle(id)}
    />
  );
}

/** "..." menu at the end of a row. Omit a prop to hide that action. */
export function RowActions({
  label,
  viewTo,
  editTo,
  onEdit,
  archived,
  onArchive,
  onRestore,
}: {
  label: string;
  viewTo: string;
  editTo?: string;
  onEdit?: () => void;
  archived?: boolean;
  onArchive?: () => void;
  onRestore?: () => void;
}) {
  const canEdit = !archived && (editTo || onEdit);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          mode="icon"
          size="sm"
          aria-label={`Actions for ${label}`}
        >
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <Link to={viewTo}>
            <Eye /> View
          </Link>
        </DropdownMenuItem>
        {canEdit &&
          (editTo ? (
            <DropdownMenuItem asChild>
              <Link to={editTo}>
                <Pencil /> Edit
              </Link>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onSelect={onEdit}>
              <Pencil /> Edit
            </DropdownMenuItem>
          ))}
        {archived
          ? onRestore && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={onRestore}>
                  <ArchiveRestore /> Restore
                </DropdownMenuItem>
              </>
            )
          : onArchive && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={onArchive}>
                  <Archive /> Archive
                </DropdownMenuItem>
              </>
            )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Bar shown above the table once rows are ticked. */
export function BulkBar({
  count,
  noun,
  archived,
  canArchive,
  onArchive,
  onRestore,
  onClear,
}: {
  count: number;
  noun: string;
  archived: boolean;
  canArchive: boolean;
  onArchive: () => void;
  onRestore: () => void;
  onClear: () => void;
}) {
  if (count === 0) return null;
  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="flex flex-wrap items-center gap-3 border-b border-border bg-primary/5 px-5 py-3"
    >
      <span className="text-sm font-medium">
        {count} {noun} selected
      </span>
      {canArchive &&
        (archived ? (
          <Button size="sm" variant="outline" onClick={onRestore}>
            <ArchiveRestore /> Restore selected
          </Button>
        ) : (
          <Button size="sm" variant="destructive" onClick={onArchive}>
            <Archive /> Archive selected
          </Button>
        ))}
      <Button size="sm" variant="ghost" onClick={onClear}>
        Clear selection
      </Button>
    </div>
  );
}

/** "Show archived" switch for a list toolbar. */
export function ShowArchived({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <Checkbox
        aria-label="Show archived"
        checked={checked}
        onCheckedChange={(v) => onChange(v === true)}
      />
      Show archived
    </label>
  );
}

interface BulkResult {
  changed: string[];
  skipped: { id: string; reason: string }[];
}

/** Archive / restore with a confirmation for archiving. Render `dialog` once on the page, then
 * call `request(ids, archive)` from a row menu or the bulk bar. `path` is the resource, e.g.
 * "/employers"; `queryKeys` are the react-query prefixes to refresh afterwards. */
export function useArchiveFlow({
  path,
  noun,
  nounPlural,
  queryKeys,
  onDone,
}: {
  path: string;
  noun: string;
  nounPlural: string;
  queryKeys: string[];
  onDone?: () => void;
}) {
  const qc = useQueryClient();
  const [pending, setPending] = useState<string[] | null>(null);
  const mutation = useMutation({
    mutationFn: ({ ids, archive }: { ids: string[]; archive: boolean }) =>
      post<BulkResult>(`${path}/${archive ? 'archive' : 'restore'}`, { ids }),
    onSuccess: (r, { archive }) => {
      const n = r.changed.length;
      const word = n === 1 ? noun : nounPlural;
      const verb = archive ? 'Archived' : 'Restored';
      if (n > 0) toast.success(`${verb} ${n} ${word}.`);
      if (r.skipped.length > 0)
        toast.warning(`${r.skipped.length} skipped: ${r.skipped[0].reason}`);
      onDone?.();
    },
    onError: (e) =>
      toast.error(
        e instanceof ApiError ? e.message : 'Could not complete the change.',
      ),
    onSettled: () => {
      for (const key of queryKeys)
        void qc.invalidateQueries({ queryKey: [key] });
    },
  });

  const request = (ids: string[], archive: boolean) => {
    if (ids.length === 0) return;
    if (archive) setPending(ids);
    else mutation.mutate({ ids, archive: false });
  };
  const n = pending?.length ?? 0;
  const dialog: ReactNode = (
    <ConfirmDialog
      open={pending !== null}
      onOpenChange={(o) => !o && setPending(null)}
      title={`Archive ${n} ${n === 1 ? noun : nounPlural}?`}
      description={`${n === 1 ? 'It' : 'They'} will be hidden from lists and reports. Nothing is deleted: an administrator can restore ${n === 1 ? 'it' : 'them'} with "Show archived".`}
      confirmLabel="Archive"
      onConfirm={() => {
        if (pending) mutation.mutate({ ids: pending, archive: true });
        setPending(null);
      }}
    />
  );
  return { request, dialog, busy: mutation.isPending };
}
