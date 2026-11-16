import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CompanyLogo } from './company-logo';

const upload = vi.fn();
const del = vi.fn();
vi.mock('@/lib/api', () => ({
  apiUrl: (p: string) => `/api/v1${p}`,
  upload: (...a: unknown[]) => upload(...a),
  del: (...a: unknown[]) => del(...a),
  ApiError: class extends Error {},
}));

function show(version: string | null, canEdit = true) {
  const onChanged = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CompanyLogo version={version} canEdit={canEdit} onChanged={onChanged} />
    </QueryClientProvider>,
  );
  return onChanged;
}
const file = (size = 10) =>
  new File([new Uint8Array(size)], 'logo.png', { type: 'image/png' });

describe('CompanyLogo', () => {
  beforeEach(() => {
    upload.mockReset().mockResolvedValue({});
    del.mockReset().mockResolvedValue(undefined);
  });

  it('shows the picture with the version so a new one is fetched', () => {
    show('123');
    expect(screen.getByAltText('Company logo')).toHaveAttribute(
      'src',
      '/api/v1/employer/logo?v=123',
    );
    expect(
      screen.getByRole('button', { name: 'Change logo' }),
    ).toBeInTheDocument();
  });

  it('offers to add one when there is none, and uploads the chosen file', async () => {
    const changed = show(null);
    expect(screen.queryByAltText('Company logo')).toBeNull();
    fireEvent.change(screen.getByLabelText('Choose a logo'), {
      target: { files: [file()] },
    });
    await waitFor(() =>
      expect(upload).toHaveBeenCalledWith('/employer/logo', {
        logo: expect.any(File),
      }),
    );
    await waitFor(() => expect(changed).toHaveBeenCalled());
  });

  it('refuses a file over 2 MB without sending it', () => {
    show(null);
    fireEvent.change(screen.getByLabelText('Choose a logo'), {
      target: { files: [file(2 * 1024 * 1024 + 1)] },
    });
    expect(screen.getByRole('alert')).toHaveTextContent('over 2 MB');
    expect(upload).not.toHaveBeenCalled();
  });

  it('removes the logo', async () => {
    const changed = show('9');
    fireEvent.click(screen.getByRole('button', { name: /Remove/ }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/employer/logo'));
    await waitFor(() => expect(changed).toHaveBeenCalled());
  });

  it('is read-only without permission to edit', () => {
    show('9', false);
    expect(screen.getByAltText('Company logo')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByLabelText('Choose a logo')).toBeNull();
  });
});
