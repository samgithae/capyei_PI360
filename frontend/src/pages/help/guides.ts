/** The Help centre's content model. Guides live in `content-*.ts`; this file holds the shape
 * and the rules for who sees what. A guide is shown only to someone who holds every
 * permission in `needs`, so a role that is edited later sees the right guides automatically. */
export interface Guide {
  /** URL part: /help/<slug>. Never change one once shared. */
  slug: string;
  title: string;
  /** One line shown on the card. */
  summary: string;
  group: GuideGroup;
  /** Permission codes the reader must hold (same codes the server checks). */
  needs: string[];
  /** The page this guide is about, so the reader can go straight there. */
  to?: { path: string; label: string };
  steps: string[];
  /** Why the system works this way, in a sentence or two. */
  why?: string;
  /** Slugs of related guides. */
  related?: string[];
  /** The opening guide for one kind of reader (only the first one the reader qualifies for shows). */
  start?: boolean;
  /** Month the guide was last checked against the system, e.g. 2026-11. */
  updated: string;
}

export const GROUPS = [
  'Getting started',
  'Set up',
  'Youth',
  'Employers and opportunities',
  'Rules',
  'Referrals',
] as const;
export type GuideGroup = (typeof GROUPS)[number];

export function canSee(g: Guide, can: (p?: string) => boolean) {
  return g.needs.every((p) => can(p));
}

/** Guides for this reader, with the single "start here" guide split out. */
export function guidesFor(all: Guide[], can: (p?: string) => boolean) {
  const mine = all.filter((g) => canSee(g, can));
  const start = mine.find((g) => g.start);
  return { start, rest: mine.filter((g) => !g.start) };
}

export function matches(g: Guide, q: string) {
  const t = q.trim().toLowerCase();
  return (
    !t ||
    [g.title, g.summary, ...g.steps].some((s) => s.toLowerCase().includes(t))
  );
}
