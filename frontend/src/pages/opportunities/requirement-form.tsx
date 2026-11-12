import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError, post } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { FormModal } from '@/components/shared/modals';
import { SelectField } from '@/components/shared/select-field';
import {
  CATEGORIES,
  problem,
  type Category,
  type Draft,
  type Lookup,
} from './requirement-model';

const NOTE: Record<Category, { label: string; placeholder: string } | null> = {
  skill: { label: 'Level needed (optional)', placeholder: 'e.g. Intermediate' },
  competency: {
    label: 'Level needed (optional)',
    placeholder: 'e.g. Intermediate',
  },
  qualification: {
    label: 'Minimum grade (optional)',
    placeholder: 'e.g. C Plain',
  },
  experience: null,
  certification: {
    label: 'What must be shown (optional)',
    placeholder: 'e.g. Copy of the certificate',
  },
  interest: null,
  working_condition: null,
  other: null,
};

const words = (s: string) =>
  s
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length >= 4);

/** Catalogue names that look like the one being added, to avoid Customer care / Customer service twins. */
export function similar(
  name: string,
  existing: { id: string; name: string }[],
) {
  const mine = words(name);
  return existing.filter((e) => {
    const theirs = words(e.name);
    return (
      e.name.toLowerCase() === name.trim().toLowerCase() ||
      mine.some((w) =>
        theirs.some(
          (t) => t.startsWith(w.slice(0, 5)) || w.startsWith(t.slice(0, 5)),
        ),
      )
    );
  });
}

function codeFor(name: string) {
  const slug = name
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 30);
  return `SK-${slug}`;
}

/** Offers the catalogue entry that is missing; only people who manage the catalogue may add. */
function AddToCatalogue({
  lookup,
  canAdd,
  onAdded,
  onUse,
}: {
  lookup: Lookup;
  canAdd: boolean;
  onAdded: (id: string) => void;
  onUse: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const twins = name.trim() ? similar(name, lookup.skills) : [];
  const add = useMutation({
    mutationFn: () =>
      post<{ id: string }>('/config/reference/skills', {
        code: codeFor(name),
        name: name.trim(),
      }),
    onSuccess: (r) => {
      toast.success('Added to the skills list.');
      setOpen(false);
      setName('');
      onAdded(r.id);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not add it.'),
  });

  if (!canAdd)
    return (
      <p className="text-xs text-muted-foreground">
        Not in the list? Ask an administrator to add it to the skills list.
      </p>
    );
  if (!open)
    return (
      <Button
        type="button"
        variant="link"
        size="sm"
        className="h-auto p-0"
        onClick={() => setOpen(true)}
      >
        Not in the list? Add a new skill
      </Button>
    );
  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <Label htmlFor="new-skill">New skill name</Label>
      <Input
        id="new-skill"
        value={name}
        maxLength={200}
        onChange={(e) => {
          setName(e.target.value);
          setError('');
        }}
      />
      {twins.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Already in the list, use one of these instead:{' '}
          {twins.map((t) => (
            <button
              key={t.id}
              type="button"
              className="me-2 text-primary underline"
              onClick={() => {
                onUse(t.id);
                setOpen(false);
                setName('');
              }}
            >
              {t.name}
            </button>
          ))}
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!name.trim() || add.isPending}
          onClick={() => add.mutate()}
        >
          {twins.length ? 'Add anyway' : 'Add to list'}
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

export function RequirementForm({
  open,
  onOpenChange,
  editing,
  draft,
  onChange,
  lookup,
  canAddSkill,
  onCatalogueChanged,
  pending,
  error,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: boolean;
  draft: Draft;
  onChange: (d: Draft) => void;
  lookup: Lookup;
  canAddSkill: boolean;
  onCatalogueChanged: () => void;
  pending: boolean;
  error: string;
  onSubmit: () => void;
}) {
  const [shown, setShown] = useState('');
  const set = (p: Partial<Draft>) => {
    setShown('');
    onChange({ ...draft, ...p });
  };
  const cat = draft.category;
  const note = NOTE[cat];
  const hint = CATEGORIES.find((c) => c.id === cat)?.hint;
  const text = shown || error;

  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title={editing ? 'Edit requirement' : 'Add requirement'}
      description="Answer three questions. The system works out how to check it."
      submitLabel={editing ? 'Save changes' : 'Add requirement'}
      pending={pending}
      error={text}
      onSubmit={() => {
        const p = problem(draft);
        setShown(p);
        if (!p) onSubmit();
      }}
    >
      <div className="space-y-1.5">
        <Label>1. What kind of requirement is it?</Label>
        <Select
          value={cat}
          onValueChange={(v) =>
            set({ category: v as Category, item: '', note: '' })
          }
        >
          <SelectTrigger aria-label="Requirement category">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CATEGORIES.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>

      <div className="space-y-1.5">
        <Label>2. What is required?</Label>
        {(cat === 'skill' || cat === 'competency') && (
          <>
            <SelectField
              label="Requirement"
              className="w-full"
              value={draft.item}
              options={lookup.skills}
              onChange={(v) => set({ item: v })}
            />
            <AddToCatalogue
              lookup={lookup}
              canAdd={canAddSkill}
              onUse={(id) => set({ item: id })}
              onAdded={(id) => {
                onCatalogueChanged();
                set({ item: id });
              }}
            />
          </>
        )}
        {cat === 'qualification' && (
          <>
            <SelectField
              label="Requirement"
              className="w-full"
              value={draft.item}
              options={lookup.levels}
              onChange={(v) => set({ item: v })}
            />
            <p className="text-xs text-muted-foreground">
              This level or higher counts. New levels are added by an
              administrator under Administration.
            </p>
          </>
        )}
        {cat === 'experience' && (
          <div className="space-y-2">
            <div className="flex gap-2">
              <Input
                aria-label="Minimum duration"
                inputMode="numeric"
                className="w-28"
                placeholder="How long"
                value={draft.duration}
                onChange={(e) => set({ duration: e.target.value })}
              />
              <Select
                value={draft.unit}
                onValueChange={(v) => set({ unit: v as Draft['unit'] })}
              >
                <SelectTrigger aria-label="Unit" className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="months">months</SelectItem>
                  <SelectItem value="years">years</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Input
              aria-label="Role or industry"
              placeholder="Role or industry (optional)"
              maxLength={120}
              value={draft.item}
              onChange={(e) => set({ item: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              Only the length is checked; the role or industry is for staff to
              read.
            </p>
          </div>
        )}
        {(cat === 'certification' || cat === 'interest') && (
          <Input
            aria-label="Requirement"
            maxLength={120}
            placeholder={
              cat === 'certification'
                ? 'e.g. Food hygiene certificate'
                : 'e.g. Retail'
            }
            value={draft.item}
            onChange={(e) => set({ item: e.target.value })}
          />
        )}
        {cat === 'working_condition' && (
          <div className="grid grid-cols-2 gap-3">
            <SelectField
              label="Work pattern"
              className="w-full"
              emptyLabel="Any pattern"
              value={draft.pattern}
              options={lookup.patterns}
              onChange={(v) => set({ pattern: v })}
            />
            <Input
              aria-label="Must be able to start by"
              type="date"
              value={draft.neededBy}
              onChange={(e) => set({ neededBy: e.target.value })}
            />
          </div>
        )}
        {cat === 'other' && (
          <Input
            aria-label="Requirement"
            maxLength={300}
            value={draft.item}
            onChange={(e) => set({ item: e.target.value })}
          />
        )}
      </div>

      {note && (
        <div className="space-y-1.5">
          <Label htmlFor="req-note">{note.label}</Label>
          <Input
            id="req-note"
            maxLength={120}
            placeholder={note.placeholder}
            value={draft.note}
            onChange={(e) => set({ note: e.target.value })}
          />
        </div>
      )}

      <fieldset className="space-y-2">
        <legend className="mb-1.5 text-sm font-medium">
          3. How important is it?
        </legend>
        {[
          {
            on: true,
            label: 'Mandatory',
            help: 'The participant is expected to meet this.',
          },
          {
            on: false,
            label: 'Preferred',
            help: 'Meeting this gives an additional advantage.',
          },
        ].map((o) => (
          <label key={o.label} className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name="req-type"
              className="mt-1"
              checked={draft.mandatory === o.on}
              onChange={() => set({ mandatory: o.on })}
            />
            <span>
              {o.label}
              <span className="block text-xs text-muted-foreground">
                {o.help}
              </span>
            </span>
          </label>
        ))}
      </fieldset>
    </FormModal>
  );
}
