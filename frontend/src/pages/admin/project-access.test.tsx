import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProjectAccess } from './project-access';

const PROJECTS = [
  { id: 'p1', code: 'P1', name: 'Project One' },
  { id: 'p2', code: 'P2', name: 'Project Two' },
];

function mockFetch() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const body = String(url).includes('/config/reference/projects')
      ? PROJECTS
      : {};
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
}

function show(scopes: { kind: string; value: string }[]) {
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ProjectAccess
        userId={7}
        username="amina"
        scopes={scopes}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return onClose;
}

afterEach(() => vi.restoreAllMocks());

describe('ProjectAccess (NEW-057)', () => {
  it('says plainly when no project is assigned', async () => {
    mockFetch();
    show([]);
    expect(await screen.findByLabelText(/Project One/)).toBeTruthy();
    expect(screen.getByTestId('project-summary').textContent).toMatch(
      /No project is assigned/,
    );
  });

  it('shows the current assignments and saves them, keeping other limits', async () => {
    const spy = mockFetch();
    show([
      { kind: 'project', value: 'p1' },
      { kind: 'region', value: 'r1' },
    ]);
    const two = await screen.findByLabelText(/Project Two/);
    expect(
      (screen.getByLabelText(/Project One/) as HTMLInputElement).checked,
    ).toBe(true);
    fireEvent.click(two);
    await waitFor(() =>
      expect(screen.getByTestId('project-summary').textContent).toMatch(
        /2 projects: Project One, Project Two/,
      ),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Save project access' }),
    );
    await waitFor(() =>
      expect(
        spy.mock.calls.some(([u]) => String(u).includes('/users/7/scopes')),
      ).toBe(true),
    );
    const put = spy.mock.calls.find(([u]) =>
      String(u).includes('/users/7/scopes'),
    )!;
    expect(JSON.parse(String(put[1]?.body)).scopes).toEqual([
      { kind: 'region', value: 'r1' },
      { kind: 'project', value: 'p1' },
      { kind: 'project', value: 'p2' },
    ]);
  });
});
