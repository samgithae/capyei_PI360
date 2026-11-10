// Small fetch wrapper for the PI 360 API (ADR-023): session cookie auth,
// CSRF header on unsafe methods, no tokens in localStorage.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

function readCookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`))
    ?.split('=')[1];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = readCookie('csrftoken');
    if (token) headers.set('X-CSRFToken', decodeURIComponent(token));
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.status === 204 ? (undefined as T) : res.json();
}

export interface Health {
  status: string;
  version: string;
}

export interface Me {
  authenticated: boolean;
  username?: string;
  roles?: string[];
}
