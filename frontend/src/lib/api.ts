// Small fetch wrapper for the PI 360 API (ADR-023): session cookie auth,
// CSRF header on unsafe methods, no tokens in localStorage.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

/** Fired on any 401 from a signed-in call so the auth provider can drop the session. */
export const UNAUTHENTICATED_EVENT = 'pi360:unauthenticated';

function readCookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`))
    ?.split('=')[1];
}

export interface FieldError {
  field: string;
  message: string;
  code: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public errors: FieldError[] = [],
    public code = '',
    /** The whole error body, for the few endpoints that return more than field errors. */
    public body: Record<string, unknown> = {},
  ) {
    super(message);
  }
  /** Message for one field, if the server named it. */
  fieldMessage(field: string): string | undefined {
    return this.errors.find((e) => e.field === field)?.message;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  // A FormData body (file upload) must set its own multipart boundary.
  if (init.body && !(init.body instanceof FormData))
    headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = readCookie('csrftoken');
    if (token) headers.set('X-CSRFToken', decodeURIComponent(token));
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  if (!res.ok) {
    let body: {
      errors?: FieldError[];
      detail?: string;
      code?: string;
      [key: string]: unknown;
    } = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    const message = body.errors?.[0]?.message ?? body.detail ?? res.statusText;
    if (res.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT));
    }
    throw new ApiError(
      res.status,
      message,
      body.errors ?? [],
      body.code ?? '',
      body,
    );
  }
  return res.status === 204 || res.status === 202
    ? (undefined as T)
    : res.json();
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });

/** Multipart upload: send a file plus text fields. */
export const upload = <T>(
  path: string,
  fields: Record<string, string | Blob>,
) => {
  const body = new FormData();
  for (const [k, v] of Object.entries(fields)) body.append(k, v);
  return api<T>(path, { method: 'POST', body });
};

/** Absolute URL of an API path, for an <img src> that rides on the session cookie. */
export const apiUrl = (path: string) => `${API_BASE}${path}`;

/** Fetch a file (the CV PDF) with the session cookie; returns the bytes and the server's file name. */
export async function apiFile(
  path: string,
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: 'include' });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.errors?.[0]?.message ?? body.detail ?? message;
    } catch {
      /* not JSON */
    }
    if (res.status === 401)
      window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT));
    throw new ApiError(res.status, message);
  }
  const named = /filename="?([^";]+)"?/.exec(
    res.headers.get('Content-Disposition') ?? '',
  );
  return { blob: await res.blob(), filename: named?.[1] ?? 'CV.pdf' };
}

/** POST a JSON body and get a file back (a table export). Same session cookie and CSRF header. */
export async function postFile(
  path: string,
  body: unknown,
): Promise<{ blob: Blob; filename: string }> {
  const token = readCookie('csrftoken');
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-CSRFToken': decodeURIComponent(token) } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let parsed: { errors?: FieldError[]; detail?: string } = {};
    try {
      parsed = await res.json();
    } catch {
      /* not JSON */
    }
    if (res.status === 401)
      window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT));
    throw new ApiError(
      res.status,
      parsed.errors?.[0]?.message ?? parsed.detail ?? res.statusText,
      parsed.errors ?? [],
    );
  }
  const named = /filename="?([^";]+)"?/.exec(
    res.headers.get('Content-Disposition') ?? '',
  );
  return { blob: await res.blob(), filename: named?.[1] ?? 'export' };
}

/** Remove a record or file: DELETE with the CSRF header, no body expected back. */
export const del = (path: string) => api<void>(path, { method: 'DELETE' });

export interface Health {
  status: string;
  version: string;
}

export interface Me {
  authenticated: boolean;
  username?: string;
  roles?: string[];
  permissions?: string[];
  scope?: Record<string, unknown>;
}
