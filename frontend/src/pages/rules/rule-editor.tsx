import { useState } from 'react';
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
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { SelectField } from '@/components/shared/select-field';
import {
  MISSING_CHOICES,
  parseValue,
  valueText,
  weightParam,
  type Definition,
  type Factor,
  type Parameter,
} from './rules-shared';

const STEPS = ['Checks', 'Numbers', 'Missing information', 'Review'];

/** Step-by-step editor for a draft rule version. It edits the same definition the JSON holds,
 * but shows plain labels and hides codes, fields and operators. */
export function RuleEditor({
  definition,
  notes,
  pending,
  error,
  onClose,
  onSave,
  onAdvanced,
}: {
  definition: Definition;
  notes: string;
  pending?: boolean;
  error?: string;
  onClose: () => void;
  onSave: (definition: Definition, changeNotes: string) => void;
  onAdvanced: () => void;
}) {
  const [step, setStep] = useState(0);
  const [d, setD] = useState<Definition>(definition);
  const [changeNotes, setChangeNotes] = useState(notes);
  const [problem, setProblem] = useState('');

  const factors = d.factors ?? [];
  const params = d.parameters ?? {};
  const on = (f: Factor) => f.enabled !== false;
  const setFactor = (code: string, patch: Partial<Factor>) =>
    setD((p) => ({
      ...p,
      factors: (p.factors ?? []).map((f) =>
        f.code === code ? { ...f, ...patch } : f,
      ),
    }));
  const setParam = (name: string, patch: object) =>
    setD((p) => ({
      ...p,
      parameters: {
        ...p.parameters,
        [name]: { ...p.parameters?.[name], ...patch } as Parameter,
      },
    }));

  // Parameters that are the weight of an enabled factor are shown as "importance".
  const weightNames = factors
    .filter(on)
    .map(weightParam)
    .filter((x): x is string => !!x && x in params);
  const otherNames = Object.keys(params).filter(
    (n) => !factors.some((f) => weightParam(f) === n),
  );
  const total = weightNames.reduce((sum, n) => {
    const v = params[n].value;
    return sum + (typeof v === 'number' ? v : 0);
  }, 0);

  const paramRow = (name: string, share?: boolean) => {
    const p = params[name];
    const num = typeof p.value === 'number' ? p.value : 0;
    return (
      <div key={name} className="space-y-1.5 rounded-md border p-3">
        <Label htmlFor={`p-${name}`} className="font-medium">
          {p.label || name}
        </Label>
        {p.note && <p className="text-xs text-muted-foreground">{p.note}</p>}
        <div className="flex flex-wrap items-center gap-3">
          <Input
            id={`p-${name}`}
            className="w-32"
            inputMode="decimal"
            value={valueText(p.value)}
            onChange={(e) => {
              const value = parseValue(e.target.value);
              setParam(name, { value, approved: value !== null });
            }}
          />
          {p.unit && (
            <span className="text-sm text-muted-foreground">
              {p.unit === 'weight' ? 'points' : p.unit}
            </span>
          )}
          {share && total > 0 && (
            <span className="text-sm text-muted-foreground">
              {Math.round((num / total) * 100)}% of the total
            </span>
          )}
        </div>
      </div>
    );
  };

  const next = () => {
    setProblem('');
    if (step === 1) {
    }
    setStep((s) => s + 1);
  };

  const waiting = Object.values(params).filter(
    (p) => p.value === null || p.value === undefined,
  ).length;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Edit draft</DialogTitle>
          <DialogDescription>
            Step {step + 1} of {STEPS.length}: {STEPS[step]}. Nothing is saved
            until the last step.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="max-h-[60vh] space-y-3 overflow-auto">
          {step === 0 && (
            <>
              <p className="text-sm text-muted-foreground">
                Choose which checks this rule uses. You can rename a check.
                Whether a requirement is mandatory or preferred is set on each
                opportunity, not here.
              </p>
              {factors.map((f) => (
                <div key={f.code} className="space-y-2 rounded-md border p-3">
                  <div className="flex items-center gap-3">
                    <Switch
                      checked={on(f)}
                      onCheckedChange={(c) => setFactor(f.code, { enabled: c })}
                      aria-label={`Use ${f.label}`}
                    />
                    <Input
                      aria-label={`Name of ${f.label}`}
                      value={f.label}
                      onChange={(e) =>
                        setFactor(f.code, { label: e.target.value })
                      }
                    />
                  </div>
                  {f.mandatory_from_requirement && (
                    <p className="ps-12 text-xs text-muted-foreground">
                      Mandatory or preferred: decided by each opportunity.
                    </p>
                  )}
                  {f.note && (
                    <details className="ps-12 text-xs text-muted-foreground">
                      <summary className="cursor-pointer">
                        More about this check
                      </summary>
                      <p className="pt-1">{f.note}</p>
                    </details>
                  )}
                </div>
              ))}
            </>
          )}

          {step === 1 && (
            <>
              {weightNames.length > 0 && (
                <>
                  <p className="text-sm font-medium">
                    How important is each check? Give points; the share of the
                    total is shown. Total: {total} points.
                  </p>
                  {weightNames.map((n) => paramRow(n, true))}
                </>
              )}
              {otherNames.length > 0 && (
                <>
                  <p className="pt-2 text-sm font-medium">
                    Limits and thresholds
                  </p>
                  {otherNames.map((n) => paramRow(n))}
                </>
              )}
              {weightNames.length + otherNames.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  This rule has no numbers to set.
                </p>
              )}
            </>
          )}

          {step === 2 && (
            <>
              <p className="text-sm text-muted-foreground">
                What should happen when a youth&apos;s record has no value for a
                check? Missing information is never treated as a failure.
              </p>
              {factors.filter(on).map((f) => (
                <div
                  key={f.code}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3"
                >
                  <div className="min-w-48 flex-1">
                    <p className="text-sm font-medium">{f.label}</p>
                    <p className="text-xs text-muted-foreground">
                      {
                        MISSING_CHOICES.find(
                          (c) => c.id === (f.unknown_policy ?? 'flag'),
                        )?.hint
                      }
                    </p>
                  </div>
                  <SelectField
                    label={`When ${f.label} is missing`}
                    className="w-56"
                    value={f.unknown_policy ?? 'flag'}
                    options={MISSING_CHOICES}
                    onChange={(v) => setFactor(f.code, { unknown_policy: v })}
                  />
                </div>
              ))}
            </>
          )}

          {step === 3 && (
            <>
              <div className="space-y-1 text-sm">
                <p className="font-medium">
                  {factors.filter(on).length} of {factors.length} checks in use
                </p>
                <ul className="list-disc ps-5">
                  {factors.filter(on).map((f) => {
                    const w = weightParam(f);
                    const v = w ? params[w]?.value : null;
                    return (
                      <li key={f.code}>
                        {f.label}
                        {typeof v === 'number' && total > 0
                          ? `: ${Math.round((v / total) * 100)}%`
                          : ''}
                        {f.unknown_policy === 'exclude'
                          ? ' (left out if missing)'
                          : ''}
                      </li>
                    );
                  })}
                </ul>
                <p role="status">
                  {waiting
                    ? `${waiting} number(s) have no value yet. You can save the draft, but it cannot be approved until each has one.`
                    : 'Every number has a value.'}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rule-notes-text">Notes for reviewers</Label>
                <Textarea
                  id="rule-notes-text"
                  value={d.notes ?? ''}
                  onChange={(e) =>
                    setD((p) => ({ ...p, notes: e.target.value }))
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rule-change-notes">What changed</Label>
                <Input
                  id="rule-change-notes"
                  maxLength={4000}
                  value={changeNotes}
                  onChange={(e) => setChangeNotes(e.target.value)}
                />
              </div>
            </>
          )}

          {(problem || error) && (
            <p role="alert" className="text-sm text-destructive">
              {problem || error}
            </p>
          )}
        </DialogBody>
        <DialogFooter className="sm:justify-between">
          <Button type="button" variant="ghost" onClick={onAdvanced}>
            Advanced: edit as JSON
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            {step > 0 && (
              <Button
                type="button"
                variant="outline"
                onClick={() => setStep(step - 1)}
              >
                Back
              </Button>
            )}
            {step < STEPS.length - 1 ? (
              <Button type="button" onClick={next}>
                Next
              </Button>
            ) : (
              <Button
                type="button"
                disabled={pending}
                onClick={() => onSave(d, changeNotes)}
              >
                {pending ? 'Saving...' : 'Save draft'}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
