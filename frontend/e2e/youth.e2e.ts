import { expect, test } from '@playwright/test';
import { signIn } from './support';

test.describe('the youth list and a youth’s page', () => {
  test('staff search the list and open a youth’s workspace', async ({
    page,
  }) => {
    await signIn(page, 'steward');
    await page.goto('/youth');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Youth', exact: true }),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Person 10' })).toBeVisible();

    // Search is by similar name, so use names that are far apart.
    await page.getByPlaceholder(/search/i).fill('Grace Akinyi');
    await page.keyboard.press('Enter');
    await expect(
      page.getByRole('link', { name: 'Grace Akinyi' }).first(),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Person 10' })).toHaveCount(0);
    await page.getByPlaceholder(/search/i).fill('Zzyzx Qwertyuiop');
    await page.keyboard.press('Enter');
    await expect(page.getByRole('link', { name: 'Grace Akinyi' })).toHaveCount(
      0,
    );

    await page.getByPlaceholder(/search/i).fill('Person 11');
    await page.keyboard.press('Enter');
    await page.getByRole('link', { name: 'Person 11' }).first().click();
    await expect(page).toHaveURL(/\/youth\/[0-9a-f-]+/);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Person 11' }),
    ).toBeVisible();
    await page.getByRole('tab', { name: 'Programme & Account' }).click();
    await expect(page).toHaveURL(/tab=account/);
  });

  test('a placement officer sees only their own caseload', async ({ page }) => {
    await signIn(page, 'officer');
    await page.goto('/youth');
    // The seed assigns the three programme-1 youth to this officer.
    await expect(page.getByRole('link', { name: /^Person 1\d$/ })).toHaveCount(
      3,
    );
    await expect(page.getByRole('link', { name: /^Person 2\d$/ })).toHaveCount(
      0,
    );
    // And no Administration menu.
    await expect(
      page.getByRole('link', { name: 'Administration' }),
    ).toHaveCount(0);
  });

  test('the data quality screen opens for a data steward', async ({ page }) => {
    await signIn(page, 'steward');
    await page.goto('/data-quality');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Data quality' }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'MIS corrections' }).click();
    await expect(
      page.getByText(/staff fix a name, gender, age/i),
    ).toBeVisible();
  });
});
