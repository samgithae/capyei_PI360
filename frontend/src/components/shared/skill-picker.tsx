import { useEffect, useState } from 'react';
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { Check, ChevronDown, ChevronRight, Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError, post } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SelectField } from '@/components/shared/select-field';

/**
 * Skills picker in the style of a job-post skills box: search, popular skills, browse by category,
 * and a "Selected skills" list. Used in two places:
 *  - an opportunity's requirements (`mode="requirement"`): each skill has a must-have switch;
 *  - a youth's profile (`mode="level"`): each skill has a level (Basic, Working, Advanced).
 *
 * Everything is read from the server a page at a time (search, category and popular endpoints under
 * `endpoint`), so the browser never holds the whole skills list. Choices stay local until the save
 * button is pressed, then `onSave` receives the whole selection.
 */

export interface PickedSkill {
  id: string;
  name: string;
  /** Opportunity requirements only. */
  mandatory?: boolean;
  /** Youth profile only: 1 Basic, 2 Working, 3 Advanced. */
  level?: number;
}
export const SKILL_LEVELS = [
  { id: '1', name: 'Basic' },
  { id: '2', name: 'Working' },
  { id: '3', name: 'Advanced' },
];
const DEFAULT_LEVEL = 2;
export const OPPORTUNITY_SKILLS = '/requirement-skills';
interface SkillRow {
  id: string;
  name: string;
  category: string;
}
interface Page {
  total: number;
  results: SkillRow[];
}
interface Category {
  name: string;
  count: number;
}
interface Popular extends SkillRow {
  used: number;
}

const PAGE = 6; // skills shown per category before "See more"
const SEARCH_PAGE = 12;
const OTHER = 'Other';

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** One server-paged list of skills: pass a search text and/or a category. */
function useSkillPages(
  endpoint: string,
  params: { q?: string; category?: string },
  on = true,
) {
  const query = useInfiniteQuery({
    queryKey: ['skill-pages', endpoint, params.q ?? '', params.category ?? ''],
    enabled: on,
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      const sp = new URLSearchParams({
        limit: String(params.q ? SEARCH_PAGE : PAGE),
        offset: String(pageParam),
      });
      if (params.q) sp.set('q', params.q);
      if (params.category) sp.set('category', params.category);
      return api<Page>(`${endpoint}?${sp}`);
    },
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.results.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });
  return {
    rows: query.data?.pages.flatMap((p) => p.results) ?? [],
    total: query.data?.pages[0]?.total ?? 0,
    loading: query.isPending && on,
    failed: query.isError,
    hasMore: !!query.hasNextPage,
    more: () => void query.fetchNextPage(),
    fetchingMore: query.isFetchingNextPage,
  };
}

function SkillChip({
  skill,
  picked,
  onToggle,
}: {
  skill: SkillRow;
  picked: boolean;
  onToggle: (s: SkillRow) => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={picked}
      onClick={() => onToggle(skill)}
      className={
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors ' +
        (picked
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-border hover:border-primary hover:text-primary')
      }
    >
      {picked ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}
      {skill.name}
    </button>
  );
}

function CategorySection({
  endpoint,
  category,
  startOpen,
  isPicked,
  onToggle,
}: {
  endpoint: string;
  category: Category;
  startOpen: boolean;
  isPicked: (id: string) => boolean;
  onToggle: (s: SkillRow) => void;
}) {
  const [open, setOpen] = useState(startOpen);
  const [expanded, setExpanded] = useState(false);
  // Only an opened category asks the server for its skills.
  const list = useSkillPages(endpoint, { category: category.name }, open);
  const shown = expanded ? list.rows : list.rows.slice(0, PAGE);
  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <section className="border-b border-border py-2 last:border-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between py-1 text-start font-medium"
      >
        <span>
          {category.name}{' '}
          <span className="text-xs font-normal text-muted-foreground">
            ({category.count})
          </span>
        </span>
        <Icon className="size-4 text-muted-foreground" />
      </button>
      {open && (
        <div className="space-y-2 pb-2 pt-1">
          {list.loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : list.failed ? (
            <p role="alert" className="text-sm text-destructive">
              Could not load this category.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {shown.map((s) => (
                <li key={s.id}>
                  <SkillChip
                    skill={s}
                    picked={isPicked(s.id)}
                    onToggle={onToggle}
                  />
                </li>
              ))}
            </ul>
          )}
          <div className="flex gap-4 text-sm">
            {(list.hasMore || (!expanded && list.rows.length > PAGE)) && (
              <button
                type="button"
                className="font-medium text-primary hover:underline"
                disabled={list.fetchingMore}
                onClick={() => {
                  // Show what is already loaded first; ask the server only for a further page.
                  const needPage =
                    list.hasMore && (expanded || list.rows.length <= PAGE);
                  setExpanded(true);
                  if (needPage) list.more();
                }}
              >
                See more
              </button>
            )}
            {expanded && list.rows.length > PAGE && (
              <button
                type="button"
                className="font-medium text-primary hover:underline"
                onClick={() => setExpanded(false)}
              >
                See less
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

/** "+ Add 'term'": adds a missing skill to the central list, with a duplicate check. */
function AddSkill({
  endpoint,
  term,
  categories,
  onAdded,
  onUse,
}: {
  endpoint: string;
  term: string;
  categories: Category[];
  onAdded: (s: SkillRow) => void;
  onUse: (s: SkillRow) => void;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState(OTHER);
  const [similar, setSimilar] = useState<SkillRow[]>([]);
  const [error, setError] = useState('');
  const add = useMutation({
    mutationFn: (confirm: boolean) =>
      post<SkillRow>(`${endpoint}/add`, {
        name: term.trim(),
        category,
        confirm_similar: confirm,
      }),
    onSuccess: (row) => {
      toast.success(`“${row.name}” added to the skills list.`);
      void qc.invalidateQueries({ queryKey: ['skill-pages', endpoint] });
      void qc.invalidateQueries({ queryKey: ['skill-categories', endpoint] });
      setOpen(false);
      onAdded(row);
    },
    onError: (e) => {
      if (!(e instanceof ApiError)) return setError('Could not add it.');
      const code = e.errors[0]?.code;
      if (code === 'exists' && e.body.existing) {
        toast.info('That skill is already in the list, so it was selected.');
        setOpen(false);
        return onUse(e.body.existing as SkillRow);
      }
      if (code === 'similar') {
        setSimilar((e.body.similar as SkillRow[]) ?? []);
        return setError('');
      }
      setError(e.message);
    },
  });

  if (!open)
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          setSimilar([]);
          setError('');
          setOpen(true);
        }}
      >
        <Plus /> Add “{term.trim()}”
      </Button>
    );
  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <p className="text-sm">
        Add <strong>{term.trim()}</strong> to the skills list, so it can be
        chosen by anyone.
      </p>
      <SelectField
        label="Category"
        className="w-full sm:w-64"
        value={category}
        options={[
          ...categories
            .filter((c) => c.name !== OTHER)
            .map((c) => ({ id: c.name, name: c.name })),
          { id: OTHER, name: OTHER },
        ]}
        onChange={(v) => setCategory(v || OTHER)}
      />
      {similar.length > 0 && (
        <div role="alert" className="text-sm">
          Similar skills already exist. Use one of them if it means the same:
          <ul className="mt-1 flex flex-wrap gap-2">
            {similar.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className="rounded-full border border-border px-3 py-1 text-primary hover:border-primary"
                  onClick={() => {
                    setOpen(false);
                    onUse(s);
                  }}
                >
                  Use {s.name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          disabled={add.isPending}
          onClick={() => add.mutate(similar.length > 0)}
        >
          {similar.length > 0 ? 'Add mine anyway' : 'Add skill'}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => setOpen(false)}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function SkillPickerDialog({
  open,
  onOpenChange,
  endpoint = OPPORTUNITY_SKILLS,
  mode = 'requirement',
  title = 'Skills for this opportunity',
  description = 'For the best results, add 3 to 5 skills. Mark the ones a youth must have; the rest count as an advantage.',
  saveLabel = 'Save skills',
  resetKey = '',
  initial,
  canAdd,
  saving,
  error,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Where the skills list is served: `<endpoint>`, `/categories`, `/popular`, `/add`. */
  endpoint?: string;
  mode?: 'requirement' | 'level';
  title?: string;
  description?: string;
  saveLabel?: string;
  /** Changes when the dialog is about to edit a different record, to start over from `initial`. */
  resetKey?: string;
  /** The skills already saved, so editing starts from them. */
  initial: PickedSkill[];
  canAdd: boolean;
  saving: boolean;
  error: string;
  onSave: (picked: PickedSkill[]) => void;
}) {
  const [picked, setPicked] = useState<PickedSkill[]>(initial);
  const [text, setText] = useState('');
  // Start from what is saved each time the dialog opens, so Discard really discards.
  useEffect(() => {
    if (open) {
      setPicked(initial);
      setText('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resetKey]);

  const q = useDebounced(text.trim());
  const searching = q.length > 0;
  const categories = useQuery({
    queryKey: ['skill-categories', endpoint],
    enabled: open,
    queryFn: () => api<{ results: Category[] }>(`${endpoint}/categories`),
  });
  const popular = useQuery({
    queryKey: ['skill-popular', endpoint],
    enabled: open,
    queryFn: () => api<{ results: Popular[] }>(`${endpoint}/popular`),
  });
  const found = useSkillPages(endpoint, { q }, open && searching);

  const fresh = (s: SkillRow): PickedSkill =>
    mode === 'level'
      ? { id: s.id, name: s.name, level: DEFAULT_LEVEL }
      : { id: s.id, name: s.name, mandatory: false };

  const isPicked = (id: string) => picked.some((p) => p.id === id);
  const toggle = (s: SkillRow) =>
    setPicked((cur) =>
      cur.some((p) => p.id === s.id)
        ? cur.filter((p) => p.id !== s.id)
        : [...cur, fresh(s)],
    );
  const select = (s: SkillRow) =>
    setPicked((cur) =>
      cur.some((p) => p.id === s.id) ? cur : [...cur, fresh(s)],
    );
  const change = (id: string, patch: Partial<PickedSkill>) =>
    setPicked((cur) => cur.map((p) => (p.id === id ? { ...p, ...patch } : p)));

  const cats = categories.data?.results ?? [];
  const exact = found.rows.some(
    (r) => r.name.toLowerCase() === q.toLowerCase(),
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogBody className="grid gap-5 overflow-y-auto md:grid-cols-[1fr_16rem]">
          <div className="min-w-0 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="skill-search">Search skills</Label>
              <Input
                id="skill-search"
                autoComplete="off"
                placeholder="Search or add a skill..."
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </div>

            {searching ? (
              <div className="space-y-3" aria-live="polite">
                {found.loading ? (
                  <p className="text-sm text-muted-foreground">Searching…</p>
                ) : found.rows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No skill matches “{q}”.
                  </p>
                ) : (
                  <>
                    <p className="text-sm text-muted-foreground">
                      {found.total} match{found.total === 1 ? '' : 'es'}
                    </p>
                    <ul className="flex flex-wrap gap-2">
                      {found.rows.map((s) => (
                        <li key={s.id}>
                          <SkillChip
                            skill={s}
                            picked={isPicked(s.id)}
                            onToggle={toggle}
                          />
                        </li>
                      ))}
                    </ul>
                    {found.hasMore && (
                      <button
                        type="button"
                        className="text-sm font-medium text-primary hover:underline"
                        disabled={found.fetchingMore}
                        onClick={found.more}
                      >
                        See more
                      </button>
                    )}
                  </>
                )}
                {!exact &&
                  !found.loading &&
                  (canAdd ? (
                    <AddSkill
                      endpoint={endpoint}
                      term={q}
                      categories={cats}
                      onAdded={select}
                      onUse={select}
                    />
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Not in the list? Ask someone who can edit to add it.
                    </p>
                  ))}
              </div>
            ) : (
              <>
                {(popular.data?.results.length ?? 0) > 0 && (
                  <section className="space-y-2">
                    <h3 className="text-sm font-medium">Popular skills</h3>
                    <ul className="flex flex-wrap gap-2">
                      {popular.data?.results.map((s) => (
                        <li key={s.id}>
                          <SkillChip
                            skill={s}
                            picked={isPicked(s.id)}
                            onToggle={toggle}
                          />
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
                <section>
                  <h3 className="mb-1 text-sm font-medium">
                    Browse by category
                  </h3>
                  {categories.isPending ? (
                    <p className="text-sm text-muted-foreground">Loading…</p>
                  ) : (
                    cats.map((c, i) => (
                      <CategorySection
                        key={c.name}
                        endpoint={endpoint}
                        category={c}
                        startOpen={i === 0}
                        isPicked={isPicked}
                        onToggle={toggle}
                      />
                    ))
                  )}
                </section>
              </>
            )}
          </div>

          <aside
            aria-label="Selected skills"
            className="space-y-2 rounded-md border border-border bg-muted/30 p-3 md:self-start"
          >
            <h3 className="text-sm font-medium">
              Selected Skills ({picked.length})
            </h3>
            {picked.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing chosen yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {picked.map((p) => (
                  <li
                    key={p.id}
                    className="rounded-md border border-border bg-background p-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium">{p.name}</span>
                      <button
                        type="button"
                        aria-label={`Remove ${p.name}`}
                        className="-m-1 rounded-full p-1 hover:text-destructive"
                        onClick={() =>
                          setPicked((cur) => cur.filter((x) => x.id !== p.id))
                        }
                      >
                        <X className="size-3.5" />
                      </button>
                    </div>
                    {mode === 'level' ? (
                      <SelectField
                        label={`Level of ${p.name}`}
                        className="mt-1 w-full"
                        value={String(p.level ?? DEFAULT_LEVEL)}
                        options={SKILL_LEVELS}
                        onChange={(v) =>
                          change(p.id, { level: Number(v) || DEFAULT_LEVEL })
                        }
                      />
                    ) : (
                      <label className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={!!p.mandatory}
                          onChange={(e) =>
                            change(p.id, { mandatory: e.target.checked })
                          }
                        />
                        Must have
                      </label>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {mode === 'requirement' && picked.length > 10 && (
              <Badge variant="warning" appearance="light">
                That is a long list: few youth will match every skill.
              </Badge>
            )}
          </aside>
        </DialogBody>
        {error && (
          <p role="alert" className="px-1 text-sm text-destructive">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Discard
          </Button>
          <Button
            type="button"
            disabled={saving}
            onClick={() => onSave(picked)}
          >
            {saving ? 'Saving...' : saveLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
