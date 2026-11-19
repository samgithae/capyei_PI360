import { expect, test } from '@playwright/test';
import { signIn } from './support';

/** T-054: consent is a setting, off until an administrator turns it on. */
test('consent tracking is off until an administrator turns it on, and goes away when turned off', async ({
  page,
}) => {
  await signIn(page, 'admin');

  // Off by default: no badge in the list, no card on the youth's page.
  await page.goto('/youth');
  await expect(page.getByRole('link', { name: 'Person 10' })).toBeVisible();
  await expect(page.getByText('No consent')).toHaveCount(0);
  await page.getByRole('link', { name: 'Person 10' }).click();
  await page.getByRole('tab', { name: 'Programme & Account' }).click();
  await expect(page.getByText('Privacy notice and consent')).toHaveCount(0);

  // Turn it on.
  await page.goto('/administration/youth-settings');
  const sw = page.getByRole('switch', { name: /privacy notice and consent/i });
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await sw.click();
  await page.getByRole('button', { name: 'Change setting' }).click();
  await expect(sw).toHaveAttribute('aria-checked', 'true');

  // Now the list warns, and the card is there.
  await page.goto('/youth');
  await expect(page.getByText('No consent').first()).toBeVisible();
  await page.getByRole('link', { name: 'Person 10' }).click();
  await page.getByRole('tab', { name: 'Programme & Account' }).click();
  await expect(page.getByText('Privacy notice and consent')).toBeVisible();

  // Record consent.
  await page.getByRole('button', { name: 'Record consent' }).click();
  await page.getByLabel('Consent status').selectOption('given');
  await page.getByLabel('Privacy notice version').fill('2026-1');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Notice version 2026-1')).toBeVisible();

  // That youth no longer shows the badge in the list.
  await page.goto('/youth');
  const row = page.getByRole('row', { name: /Person 10/ });
  await expect(row).toBeVisible();
  await expect(row.getByText('No consent')).toHaveCount(0);

  // Turn it off again: everything disappears (what was recorded is kept).
  await page.goto('/administration/youth-settings');
  await sw.click();
  await page.getByRole('button', { name: 'Change setting' }).click();
  await expect(sw).toHaveAttribute('aria-checked', 'false');
  await page.goto('/youth');
  await expect(page.getByRole('link', { name: 'Person 10' })).toBeVisible();
  await expect(page.getByText('No consent')).toHaveCount(0);
});
