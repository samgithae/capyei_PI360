import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { LoadingState } from '@/components/states';

export interface Scope {
  kind: string;
  value: string;
}
interface Project {
  id: string;
  code: string;
  name: string;
}

/** NEW-057: choose the projects a staff member works in. Other kinds of scope (cohort, region,
 * own caseload) are kept as they are. A Project officer with no project sees nothing (D-085). */
export function ProjectAccess({
  userId,
  username,
  scopes,
  onClose,
}: {
  userId: number;
  username: string;
  scopes: Scope[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const projects = useQuery({
    queryKey: ['reference', 'projects'],
    queryFn: () => api<Project[]>('/config/reference/projects'),
  });
  const others = scopes.filter((s) => s.kind !== 'project');
  const [chosen, setChosen] = useState(
    () =>
      new Set(scopes.filter((s) => s.kind === 'project').map((s) => s.value)),
  );
  const [error, setError] = useState('');

  const save = useMutation({
    mutationFn: () =>
      api(`/identity/users/${userId}/scopes`, {
        method: 'PUT',
        body: JSON.stringify({
          scopes: [
            ...others,
            ...[...chosen].map((value) => ({ kind: 'project', value })),
          ],
        }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['users'] });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Failed'),
  });

  const toggle = (id: string) => {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setChosen(next);
  };
  const names = (projects.data ?? [])
    .filter((p) => chosen.has(p.id))
    .map((p) => p.name);

  return (
    <form
      className="rounded-md border p-4 space-y-3 max-w-md"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h2 className="font-medium">Project access for {username}</h2>
      <p
        className="text-sm text-muted-foreground"
        data-testid="project-summary"
      >
        {chosen.size === 0
          ? 'No project is assigned. A Project officer with no project sees no youth.'
          : `Assigned to ${chosen.size} project${chosen.size === 1 ? '' : 's'}: ${
              names.join(', ') || '…'
            }.`}
      </p>
      {others.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Other limits on this account ({others.map((s) => s.kind).join(', ')})
          are kept.
        </p>
      )}
      {projects.isPending && <LoadingState />}
      <fieldset className="space-y-2">
        <legend className="sr-only">Projects</legend>
        {(projects.data ?? []).map((p) => (
          <label key={p.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={chosen.has(p.id)}
              onChange={() => toggle(p.id)}
            />
            {p.name} <span className="text-muted-foreground">({p.code})</span>
          </label>
        ))}
      </fieldset>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          Save project access
        </Button>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
