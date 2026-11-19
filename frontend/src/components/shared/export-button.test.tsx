import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExportButton } from './export-button';

const postFile = vi.fn();
const saveBlob = vi.fn();
let permissions: string[] = [];
vi.mock('@/lib/api', () => ({
  postFile: (...a: unknown[]) => postFile(...a),
  ApiError: class extends Error {},
}));
vi.mock('@/auth/auth-context', () => ({
  useAuth: () => ({ can: (p: string) => permissions.includes(p) }),
}));
vi.mock('@/pages/participants/cv/download-cv-button', () => ({
  saveBlob: (...a: unknown[]) => saveBlob(...a),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function show(search = 'county=c1&status=active&page=3&sort=name') {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ExportButton
        table="youth"
        params={new URLSearchParams(search)}
        noun="youth"
        total={12}
      />
    </QueryClientProvider>,
  );
}

describe('ExportButton', () => {
  beforeEach(() => {
    postFile.mockReset();
    saveBlob.mockReset();
    permissions = [];
  });

  it('is hidden without the restricted permission', () => {
    show();
    expect(screen.queryByRole('button', { name: /export/i })).toBeNull();
  });

  it('asks for a purpose before it downloads', () => {
    permissions = ['exports.identifiable'];
    show();
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    expect(screen.getByText(/12 youth matching/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    expect(screen.getByRole('alert').textContent).toMatch(
      /what the file is for/i,
    );
    expect(postFile).not.toHaveBeenCalled();
  });

  it('sends the current filters but not the page or sort', async () => {
    permissions = ['exports.identifiable'];
    postFile.mockResolvedValue({ blob: new Blob(['x']), filename: 'a.csv' });
    show();
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    fireEvent.change(screen.getByLabelText(/what is this file for/i), {
      target: { value: 'Mombasa calls' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    await waitFor(() => expect(postFile).toHaveBeenCalled());
    const [path, body] = postFile.mock.calls[0];
    expect(path).toBe('/exports/table/youth?county=c1&status=active');
    expect(body).toEqual({ format: 'csv', purpose: 'Mombasa calls' });
    await waitFor(() => expect(saveBlob).toHaveBeenCalled());
  });
});
