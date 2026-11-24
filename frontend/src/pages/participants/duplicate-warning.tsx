import { Link } from 'react-router';

export interface SimilarMatch {
  id: string;
  name: string;
  status: string;
  county: string;
  projects: string[];
  reasons: { code: string; text: string }[];
}

/** "Someone like this is already in the directory" (T-055). It only warns: the person adding
 * the youth decides, and can open each match in a new tab to compare before going on. */
export function DuplicateWarning({
  matches,
  onContinue,
  continueLabel = 'continue anyway',
}: {
  matches: SimilarMatch[];
  onContinue: () => void;
  continueLabel?: string;
}) {
  if (matches.length === 0) return null;
  return (
    <div
      role="alert"
      className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm"
    >
      <p className="font-medium">
        {matches.length === 1
          ? 'Someone like this is already in the directory.'
          : 'People like this are already in the directory.'}
      </p>
      <ul className="space-y-1.5">
        {matches.map((m) => (
          <li key={m.id}>
            <Link
              to={`/youth/${m.id}`}
              target="_blank"
              rel="noreferrer"
              className="font-medium underline"
            >
              {m.name}
            </Link>{' '}
            <span className="text-muted-foreground">
              (
              {[m.status, m.county, ...m.projects].filter(Boolean).join(', ')}
              )
            </span>
            <br />
            <span className="text-xs text-muted-foreground">
              {m.reasons.map((r) => r.text).join('; ')}
            </span>
          </li>
        ))}
      </ul>
      <p>
        If this is a different person,{' '}
        <button
          type="button"
          className="font-medium underline"
          onClick={onContinue}
        >
          {continueLabel}
        </button>
        .
      </p>
    </div>
  );
}
