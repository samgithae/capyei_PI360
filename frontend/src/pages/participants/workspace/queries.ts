import { useAuth } from '@/auth/auth-context';
import type {
  ReferralPage,
  ReferralRow,
} from '@/pages/referrals/referral-shared';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { CvDoc, CvProfileData } from '../cv/cv-types';

// The workspace tabs share these queries (same keys as the CV components), so switching
// tabs reads the cache and never refetches the same record twice.

/** The CV document as an employer reads it (headline, photo flag, completeness). */
export function useCv(id: string) {
  const { can } = useAuth();
  return useQuery({
    queryKey: ['participant-cv', id],
    queryFn: () => api<CvDoc>(`/participants/${id}/cv`),
    enabled: can('participants.view_profile'),
    retry: false,
  });
}

/** The editable profile records, with who entered each and how staff checked it. */
export function useProfile(id: string) {
  const { can } = useAuth();
  return useQuery({
    queryKey: ['participant-profile', id],
    queryFn: () => api<CvProfileData>(`/participants/${id}/profile`),
    enabled: can('participants.view_profile'),
    retry: false,
  });
}

/** Referrals of this youth; no request at all for roles that may not see referrals. */
export function useParticipantReferrals(id: string) {
  const { can } = useAuth();
  return useQuery({
    queryKey: ['referrals', 'participant', id],
    queryFn: () => api<ReferralPage>(`/referrals?participant=${id}`),
    enabled: can('referrals.view'),
  });
}

export type { ReferralRow };
