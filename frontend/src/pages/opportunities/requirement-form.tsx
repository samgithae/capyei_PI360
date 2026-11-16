import { useState } from 'react';
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
  skill: null,
  competency: null,
  qualification: null,
  experience: null,
  certification: {
    label: 'What must be shown (optional)',
    placeholder: 'e.g. Copy of the certificate',
  },
  interest: null,
  working_condition: null,
  other: null,
};

export function RequirementForm({
  open,
  onOpenChange,
  editing,
  draft,
  onChange,
  lookup,
  onPickSkills,
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
  /** Skills and competencies are chosen in the skills picker, not in this form. */
  onPickSkills: () => void;
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
      description="Answer a few questions. The system works out how to check it."
      submitLabel={editing ? 'Save changes' : 'Add requirement'}
      pending={pending}
      error={text}
      onSubmit={() => {
        if (cat === 'skill' || cat === 'competency') return onPickSkills();
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
            set({
              category: v as Category,
              item: '',
              minGrade: '',
              note: '',
            })
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
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Skills and competencies are chosen together: search, pick several
              at once, add one that is missing, and mark the must-haves.
            </p>
            <Button type="button" variant="outline" onClick={onPickSkills}>
              Choose skills
            </Button>
          </div>
        )}
        {cat === 'qualification' && (
          <>
            <SelectField
              label="Requirement"
              className="w-full"
              value={draft.item}
              options={lookup.levels}
              onChange={(v) => set({ item: v, minGrade: '' })}
            />
            {(lookup.grades ?? []).some((g) => g.level_id === draft.item) && (
              <SelectField
                label="Minimum grade"
                className="w-full"
                value={draft.minGrade}
                emptyLabel="Any grade"
                options={(lookup.grades ?? [])
                  .filter((g) => g.level_id === draft.item)
                  .sort((a, b) => a.rank - b.rank)}
                onChange={(v) => set({ minGrade: v })}
              />
            )}
            <p className="text-xs text-muted-foreground">
              A youth with this level and the minimum grade or better counts,
              and so does anyone with a higher level. A youth with no grade
              recorded shows as unknown, not failed. Levels and grades are
              managed by an administrator under Administration.
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

      {cat !== 'skill' && cat !== 'competency' && (
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
      )}
    </FormModal>
  );
}
