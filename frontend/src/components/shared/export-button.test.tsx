import type { ComponentProps } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExportButton } from './export-button';

// jsdom has no ResizeObserver, which Radix checkboxes use to measure themselves.
vi.stubGlobal(
  'ResizeObserver',
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

const postFile = vi.fn();
const getFields = vi.fn();
const saveBlob = vi.fn();
let permissions: string[] = [];
const GROUPS = {
  groups: [
    {
      key: 'identity',
      label: 'Identity',
      fields: [
        { key: 'name', label: 'Name', sensitive: false },
        { key: 'date_of_birth', label: 'Date of birth', sensitive: true },
      ],
    },
    {
      key: 'contact',
      label: 'Contact',
      fields: [{ key: 'phone', label: 'Phone', sensitive: true }],
    },
  ],
};
vi.mock('@/lib/api', () => ({
  api: (...a: unknown[]) => getFields(...a),
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

function show(
  search = 'county=c1&status=active&page=3&sort=name',
  table: ComponentProps<typeof ExportButton>['table'] = 'youth',
) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ExportButton
        table={table}
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
    getFields.mockReset();
    getFields.mockResolvedValue(GROUPS);
    saveBlob.mockReset();
    permissions = [];
  });

  it('is hidden without the restricted permission', () => {
    show();
    expect(screen.queryByRole('button', { name: /export/i })).toBeNull();
  });

  it('asks for a purpose before it downloads', async () => {
    permissions = ['exports.identifiable'];
    show();
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    expect(screen.getByText(/12 youth matching/i)).toBeTruthy();
    await screen.findByLabelText('Phone');
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
    await screen.findByLabelText('Phone');
    fireEvent.change(screen.getByLabelText(/what is this file for/i), {
      target: { value: 'Mombasa calls' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    await waitFor(() => expect(postFile).toHaveBeenCalled());
    const [path, body] = postFile.mock.calls[0];
    expect(path).toBe('/exports/table/youth?county=c1&status=active');
    // Nothing was unticked, so every field goes.
    expect(body).toEqual({
      format: 'csv',
      purpose: 'Mombasa calls',
      fields: ['name', 'date_of_birth', 'phone'],
    });
    await waitFor(() => expect(saveBlob).toHaveBeenCalled());
  });

  it('sends each table its own filters only', async () => {
    permissions = ['exports.identifiable'];
    postFile.mockResolvedValue({ blob: new Blob(['x']), filename: 'a.csv' });
    // `county` is an employers filter, `stage` belongs to referrals, `sort` to neither.
    show('stage=active&mine=1&county=c1&sort=name', 'referrals');
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    await screen.findByLabelText('Phone');
    fireEvent.change(screen.getByLabelText(/what is this file for/i), {
      target: { value: 'Review' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    await waitFor(() => expect(postFile).toHaveBeenCalled());
    expect(postFile.mock.calls[0][0]).toBe(
      '/exports/table/referrals?stage=active&mine=1',
    );
  });

  it('says whether the file holds names', () => {
    permissions = ['exports.identifiable'];
    show('q=acme', 'employers');
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    expect(screen.getByText(/no names of young people/i)).toBeTruthy();
  });

  it('starts with every field ticked and flags the sensitive ones', async () => {
    permissions = ['exports.identifiable'];
    show();
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    const phone = await screen.findByLabelText('Phone');
    expect(phone.getAttribute('data-state')).toBe('checked');
    expect(screen.getByLabelText('Name').getAttribute('data-state')).toBe(
      'checked',
    );
    expect(screen.getAllByText('Sensitive')).toHaveLength(2);
    expect(screen.getByText('3 of 3 selected')).toBeTruthy();
    expect(getFields).toHaveBeenCalledWith('/exports/fields/youth');
  });

  it('sends only the fields that stay ticked', async () => {
    permissions = ['exports.identifiable'];
    postFile.mockResolvedValue({ blob: new Blob(['x']), filename: 'a.csv' });
    show();
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    // Untick the whole Contact group and one field of Identity.
    fireEvent.click(await screen.findByLabelText('Contact'));
    fireEvent.click(screen.getByLabelText('Date of birth'));
    expect(screen.getByText('1 of 3 selected')).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/what is this file for/i), {
      target: { value: 'Outreach' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    await waitFor(() => expect(postFile).toHaveBeenCalled());
    expect(postFile.mock.calls[0][1].fields).toEqual(['name']);
  });

  it('will not download with no field chosen', async () => {
    permissions = ['exports.identifiable'];
    show();
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    await screen.findByLabelText('Phone');
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    fireEvent.change(screen.getByLabelText(/what is this file for/i), {
      target: { value: 'Outreach' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    expect(screen.getByRole('alert').textContent).toMatch(
      /at least one field/i,
    );
    expect(postFile).not.toHaveBeenCalled();
  });

  it('offers the same picker on the other tables, asking for that table', async () => {
    permissions = ['exports.identifiable'];
    postFile.mockResolvedValue({ blob: new Blob(['x']), filename: 'a.csv' });
    show('q=acme', 'employers');
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    await screen.findByLabelText('Phone');
    expect(getFields).toHaveBeenCalledWith('/exports/fields/employers');
    fireEvent.click(screen.getByLabelText('Date of birth'));
    fireEvent.change(screen.getByLabelText(/what is this file for/i), {
      target: { value: 'Review' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    await waitFor(() => expect(postFile).toHaveBeenCalled());
    expect(postFile.mock.calls[0][1]).toEqual({
      format: 'csv',
      purpose: 'Review',
      fields: ['name', 'phone'],
    });
  });

  it('sends the corrections list its state and name filters', async () => {
    permissions = ['exports.identifiable'];
    postFile.mockResolvedValue({ blob: new Blob(['x']), filename: 'a.csv' });
    show('state=conflict&q=ann&offset=20&programme=p1', 'corrections');
    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    await screen.findByLabelText('Phone');
    expect(getFields).toHaveBeenCalledWith('/exports/fields/corrections');
    fireEvent.change(screen.getByLabelText(/what is this file for/i), {
      target: { value: 'MIS update' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Download' }));
    await waitFor(() => expect(postFile).toHaveBeenCalled());
    expect(postFile.mock.calls[0][0]).toBe(
      '/exports/table/corrections?state=conflict&q=ann',
    );
  });
});
