import { useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Building2, X } from 'lucide-react';
import { ApiError, apiUrl, del, upload } from '@/lib/api';
import { Button } from '@/components/ui/button';

export const LOGO_PATH = '/employer/logo';
const MAX_BYTES = 2 * 1024 * 1024;

const message = (e: unknown) =>
  e instanceof ApiError ? e.message : 'Could not save the logo. Try again.';

/** The company's logo with buttons to add, change or remove it (when allowed to edit). The
 *  picture rides on the session cookie; `version` changes with each upload so a new one shows. */
export function CompanyLogo({
  version,
  canEdit,
  onChanged,
}: {
  version: string | null;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState('');
  const has = version !== null;
  const send = useMutation({
    mutationFn: (file: File) => upload(LOGO_PATH, { logo: file }),
    onSuccess: onChanged,
    onError: (e) => setError(message(e)),
  });
  const remove = useMutation({
    mutationFn: () => del(LOGO_PATH),
    onSuccess: onChanged,
    onError: (e) => setError(message(e)),
  });
  return (
    <div className="flex items-center gap-4">
      {has ? (
        <img
          src={`${apiUrl(LOGO_PATH)}?v=${version}`}
          alt="Company logo"
          className="size-24 rounded-md border border-border bg-white object-contain p-1"
        />
      ) : (
        <div
          aria-label="No logo yet"
          className="flex size-24 items-center justify-center rounded-md bg-muted text-muted-foreground"
        >
          <Building2 className="size-9" />
        </div>
      )}
      <div className="space-y-1 text-sm">
        <p className="text-muted-foreground">
          {canEdit
            ? 'A PNG, JPG or WebP image, up to 2 MB. It is resized to fit, never cropped.'
            : has
              ? ''
              : 'No logo has been added yet.'}
        </p>
        {canEdit && (
          <>
            <input
              ref={input}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              aria-label="Choose a logo"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (!file) return;
                setError('');
                if (file.size > MAX_BYTES)
                  return setError('That logo is over 2 MB.');
                send.mutate(file);
              }}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={send.isPending}
                onClick={() => input.current?.click()}
              >
                {send.isPending
                  ? 'Uploading...'
                  : has
                    ? 'Change logo'
                    : 'Add logo'}
              </Button>
              {has && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={remove.isPending}
                  onClick={() => {
                    setError('');
                    remove.mutate();
                  }}
                >
                  <X /> Remove
                </Button>
              )}
            </div>
          </>
        )}
        {error && (
          <p role="alert" className="text-destructive">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
