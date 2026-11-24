import { test } from '@playwright/test';
import { expectAccessible, signIn } from './support';

/**
 * T-050: automated accessibility checks (axe, WCAG 2.1 A and AA). Each screen is opened as a
 * person who uses it and scanned once its content has loaded. Serious and critical problems fail
 * the run; lesser ones are printed. Axe finds roughly a third of accessibility problems, so this
 * complements, and does not replace, keyboard and screen-reader checks by hand.
 */
test('the sign-in page', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username').waitFor();
  await expectAccessible(page, '/login');
});

const SCREENS: [
  who: 'admin' | 'steward' | 'officer',
  path: string,
  ready: string | RegExp,
][] = [
  ['admin', '/', 'Project dashboard'],
  ['steward', '/youth', 'Youth'],
  ['steward', '/data-quality', 'Data quality'],
  ['steward', '/duplicates', 'Duplicates'],
  ['steward', '/imports', 'Imports'],
  ['admin', '/employers', 'Employers'],
  ['admin', '/opportunities', 'Opportunities'],
  ['admin', '/referrals', 'Referrals'],
  ['admin', '/cases', 'Cases'],
  ['admin', '/placements', 'Placements'],
  ['admin', '/followups', 'Follow-ups'],
  ['admin', '/rules', 'Rules'],
  ['admin', '/help', /help/i],
  ['admin', '/administration/users', 'Staff accounts'],
  ['admin', '/administration/youth-settings', 'Youth record settings'],
  ['admin', '/administration/employer-portal', 'Employer portal settings'],
];

for (const [who, path, ready] of SCREENS) {
  test(`${path} as ${who}`, async ({ page }) => {
    await signIn(page, who);
    await page.goto(path);
    await page.getByRole('heading', { level: 1, name: ready }).waitFor();
    await page.waitForLoadState('networkidle');
    await expectAccessible(page, path);
  });
}

test('a youth’s page, on each tab', async ({ page }) => {
  await signIn(page, 'steward');
  await page.goto('/youth');
  await page.getByRole('link', { name: 'Person 10' }).click();
  await page.getByRole('tab').first().waitFor();
  const tabs = await page.getByRole('tab').all();
  for (const tab of tabs) {
    await tab.click();
    await page.waitForLoadState('networkidle');
    await expectAccessible(page, `youth page, tab ${await tab.innerText()}`);
  }
});
