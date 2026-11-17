import { useState } from 'react';
import { useAuth } from '@/auth/auth-context';
import { ReferDialog } from '@/pages/referrals/referral-shared';
import { useQuery } from '@tanstack/react-query';
import { Helmet } from 'react-helmet-async';
import { Link, useParams, useSearchParams } from 'react-router';
import { api, ApiError } from '@/lib/api';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useArchiveFlow } from '@/components/shared/bulk';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { CvProfile } from './cv/cv-profile';
import { AccountTab } from './workspace/account-tab';
import { IdentityHeader } from './workspace/header';
import { HistoryTab } from './workspace/history-tab';
import { OverviewTab } from './workspace/overview-tab';
import type { TabId } from './workspace/readiness';
import { ReferralsTab } from './workspace/referrals-tab';
import type { Detail } from './workspace/types';
import { VerificationTab } from './workspace/verification-tab';

const TABS: { id: TabId; label: string; needs?: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'cv', label: 'CV Profile', needs: 'participants.view_profile' },
  {
    id: 'history',
    label: 'Education & Experience',
    needs: 'participants.view_profile',
  },
  {
    id: 'skills',
    label: 'Skills & Verification',
    needs: 'participants.view_profile',
  },
  { id: 'referrals', label: 'Referrals & Placement', needs: 'referrals.view' },
  { id: 'account', label: 'Programme & Account' },
];

/**
 * The youth workspace: who they are (header) and six tabs for everything staff do with them.
 * The tab lives in the address (`?tab=`), so it can be linked and survives a refresh, and
 * switching tabs never reloads the page.
 */
export function ProfilePage() {
  const { id } = useParams();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [referring, setReferring] = useState(false);
  const archive = useArchiveFlow({
    path: '/participants',
    noun: 'participant',
    nounPlural: 'participants',
    queryKeys: ['participant', 'participants'],
  });
  const q = useQuery({
    queryKey: ['participant', id],
    queryFn: () => api<Detail>(`/participants/${id}`),
    retry: false,
  });

  const tabs = TABS.filter((t) => !t.needs || can(t.needs));
  const asked = params.get('tab');
  const tab: TabId = tabs.some((t) => t.id === asked)
    ? (asked as TabId)
    : 'overview';
  const go = (next: string) =>
    setParams(
      (old) => {
        const n = new URLSearchParams(old);
        if (next === 'overview') n.delete('tab');
        else n.set('tab', next);
        return n;
      },
      { replace: true },
    );

  if (q.isError) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="container-fluid space-y-3">
        {missing ? (
          <EmptyState
            title="Participant not found"
            hint="It may have been removed or the link is wrong."
          />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
        <Link className="text-primary" to="/youth">
          Back to directory
        </Link>
      </div>
    );
  }
  const p = q.data;
  if (!p) return <LoadingState />;

  return (
    <div className="container-fluid space-y-5">
      <Helmet>
        <title>{p.name} | PI 360</title>
      </Helmet>
      <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
        <Link className="hover:text-primary" to="/youth">
          Youth
        </Link>{' '}
        / <span className="break-words text-foreground">{p.name}</span>
      </nav>
      {archive.dialog}
      <ReferDialog
        open={referring}
        onOpenChange={setReferring}
        participant={{ id: p.id, name: p.name }}
      />
      <IdentityHeader
        p={p}
        onRefer={() => setReferring(true)}
        onArchive={() => archive.request([p.id], !p.archived)}
        onViewCv={() => go('cv')}
      />

      <Tabs value={tab} onValueChange={go} className="space-y-5">
        <div className="overflow-x-auto">
          <TabsList
            variant="line"
            className="w-max min-w-full flex-nowrap"
            aria-label="Youth profile sections"
          >
            {tabs.map((t) => (
              <TabsTrigger
                key={t.id}
                value={t.id}
                className="whitespace-nowrap"
              >
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="overview">
          <OverviewTab p={p} go={(t) => go(t)} />
        </TabsContent>
        {can('participants.view_profile') && (
          <>
            <TabsContent value="cv">
              <CvProfile id={p.id} />
            </TabsContent>
            <TabsContent value="history">
              <HistoryTab p={p} />
            </TabsContent>
            <TabsContent value="skills">
              <VerificationTab id={p.id} />
            </TabsContent>
          </>
        )}
        <TabsContent value="referrals">
          <ReferralsTab p={p} onRefer={() => setReferring(true)} />
        </TabsContent>
        <TabsContent value="account">
          <AccountTab p={p} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
