import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ALL_GUIDES } from './all-guides';
import { canSee, GROUPS, guidesFor } from './guides';

const catalogue = readFileSync(
  resolve(process.cwd(), '../backend/apps/identity/catalogue.py'),
  'utf8',
);
const known = new Set(
  [...catalogue.matchAll(/Permission\(\s*"([\w.]+)"/g)].map((m) => m[1]),
);
const routing = readFileSync(
  resolve(process.cwd(), 'src/routing/app-routing-setup.tsx'),
  'utf8',
);
const paths = new Set(
  [...routing.matchAll(/path="([^"]+)"/g)].map((m) => m[1]),
);
const defined = (p: string) =>
  paths.has(p) || p === '/administration/programmes';

describe('help guides', () => {
  it('have unique slugs and known groups', () => {
    const slugs = ALL_GUIDES.map((g) => g.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    for (const g of ALL_GUIDES) expect(GROUPS).toContain(g.group);
  });

  it('only name permissions that exist on the server', () => {
    expect(known.size).toBeGreaterThan(20);
    for (const g of ALL_GUIDES)
      for (const p of g.needs) expect(known, `${g.slug}: ${p}`).toContain(p);
  });

  it('link only to pages that exist', () => {
    for (const g of ALL_GUIDES)
      if (g.to)
        expect(defined(g.to.path), `${g.slug}: ${g.to.path}`).toBe(true);
  });

  it('reference only guides that exist', () => {
    const slugs = new Set(ALL_GUIDES.map((g) => g.slug));
    for (const g of ALL_GUIDES)
      for (const r of g.related ?? [])
        expect(slugs, `${g.slug}: ${r}`).toContain(r);
  });

  it('show a youth only youth guides', () => {
    const can = (p?: string) => !p || p === 'youth.self_service';
    const { start, rest } = guidesFor(ALL_GUIDES, can);
    expect(start?.slug).toBe('youth-start');
    expect(rest.length).toBeGreaterThan(0);
    for (const g of rest) expect(g.needs).toEqual(['youth.self_service']);
  });

  it('show an officer referral guides but not set-up guides', () => {
    const allowed = new Set([
      'referrals.view',
      'referrals.edit',
      'employers.view',
    ]);
    const can = (p?: string) => !p || allowed.has(p);
    const { start, rest } = guidesFor(ALL_GUIDES, can);
    expect(start?.slug).toBe('officer-start');
    const slugs = rest.map((g) => g.slug);
    expect(slugs).toContain('refer-youth');
    expect(slugs).not.toContain('set-up-reference-lists');
    expect(slugs).not.toContain('youth-add-skills');
  });

  it('show an administrator everything except the youth portal guides', () => {
    const can = (p?: string) => p !== 'youth.self_service';
    const visible = ALL_GUIDES.filter((g) => canSee(g, can));
    expect(visible.some((g) => g.slug === 'create-youth')).toBe(true);
    expect(visible.some((g) => g.slug === 'youth-add-skills')).toBe(false);
  });
});
