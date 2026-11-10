import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, Me, post, UNAUTHENTICATED_EVENT } from '@/lib/api';

export type LoginResult = {
  status: 'ok' | 'mfa_required';
  mfa_enrolled?: boolean;
};

interface AuthState {
  me: Me | undefined;
  loading: boolean;
  authenticated: boolean;
  /** True when the signed-in user holds the permission. Hiding UI is a convenience only: the API enforces it. */
  can: (permission?: string) => boolean;
  login: (username: string, password: string) => Promise<LoginResult>;
  verifyMfa: (code: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<unknown>;
}

const AuthContext = createContext<AuthState | null>(null);
const ME_KEY = ['me'];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ME_KEY,
    queryFn: () => api<Me>('/me'),
    staleTime: 60_000,
    retry: false,
  });
  const me = query.data;

  // Any 401 elsewhere means the session ended (timeout, suspension, sign-out elsewhere).
  useEffect(() => {
    const onExpired = () => {
      qc.setQueryData<Me>(ME_KEY, { authenticated: false });
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' });
    };
    window.addEventListener(UNAUTHENTICATED_EVENT, onExpired);
    return () => window.removeEventListener(UNAUTHENTICATED_EVENT, onExpired);
  }, [qc]);

  const refresh = useCallback(
    () => qc.invalidateQueries({ queryKey: ME_KEY }),
    [qc],
  );

  const value = useMemo<AuthState>(() => {
    const perms = new Set(me?.permissions ?? []);
    return {
      me,
      loading: query.isLoading,
      authenticated: !!me?.authenticated,
      can: (p) => !p || perms.has(p),
      login: async (username, password) => {
        const r = await post<LoginResult>('/auth/login', {
          username,
          password,
        });
        if (r.status === 'ok') await refresh();
        return r;
      },
      verifyMfa: async (code) => {
        await post('/auth/mfa/verify', { code });
        await refresh();
      },
      logout: async () => {
        await post('/auth/logout');
        qc.clear();
        qc.setQueryData<Me>(ME_KEY, { authenticated: false });
      },
      refresh,
    };
  }, [me, query.isLoading, qc, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
