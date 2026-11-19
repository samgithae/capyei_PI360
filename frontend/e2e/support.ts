import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

/** Accounts made by backend/scripts/seed_dev.py. Synthetic: never real people. */
export const USERS = {
  admin: { username: 'dev.admin', password: 'dev-admin-password-1' },
  steward: { username: 'dev.steward', password: 'dev-steward-password-1' },
  officer: { username: 'dev.officer', password: 'dev-officer-password' },
  manager: { username: 'dev.viewer', password: 'dev-viewer-password-1' },
} as const;

export async function signIn(page: Page, who: keyof typeof USERS) {
  const { username, password } = USERS[who];
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByLabel('Username')).toHaveCount(0);
}

/**
 * Fail on accessibility problems axe rates serious or critical (WCAG 2.1 A and AA). Minor and
 * moderate ones are reported in the test output but do not fail the run.
 */
export async function expectAccessible(page: Page, where: string) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const text = (v: (typeof violations)[number]) =>
    `${v.impact} ${v.id}: ${v.help} (${v.nodes.length} element(s), e.g. ${v.nodes[0]?.target.join(' ')})`;
  const lesser = violations.filter(
    (v) => !['serious', 'critical'].includes(v.impact ?? ''),
  );
  if (lesser.length)
    console.log(`axe, ${where}, not failing:\n` + lesser.map(text).join('\n'));
  expect(
    violations
      .filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))
      .map(text),
    `accessibility problems on ${where}`,
  ).toEqual([]);
}
