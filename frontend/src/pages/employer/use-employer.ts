import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { EmployerMe } from './employer-types';

/** Who is signed in and which company they belong to (cached for every portal page). */
export function useEmployerMe() {
  return useQuery({
    queryKey: ['employer-me'],
    queryFn: () => api<EmployerMe>('/employer/me'),
    staleTime: 5 * 60_000,
  });
}
