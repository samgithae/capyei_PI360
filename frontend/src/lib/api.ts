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
  if (init.body) headers.set('Content-Type', 'application/json');
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
    let body: { errors?: FieldError[]; detail?: string; code?: string } = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    const message = body.errors?.[0]?.message ?? body.detail ?? res.statusText;
    if (res.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT));
    }
    throw new ApiError(res.status, message, body.errors ?? [], body.code ?? '');
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
