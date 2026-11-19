import { expect, test } from '@playwright/test';
import { signIn, USERS } from './support';

test.describe('signing in and out', () => {
  test('a visitor who is not signed in is sent to the sign-in page', async ({
    page,
  }) => {
    await page.goto('/youth');
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  });

  test('a wrong password is refused with a message and stays on the page', async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByLabel('Username').fill(USERS.admin.username);
    await page.getByLabel('Password', { exact: true }).fill('not-the-password');
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test('an administrator signs in, then out again', async ({ page }) => {
    await signIn(page, 'admin');
    await expect(page).not.toHaveURL(/\/login/);
    await page
      .getByRole('button', { name: USERS.admin.username })
      .first()
      .click();
    await page.getByText('Sign out').click();
    await expect(page).toHaveURL(/\/login/);
    // Signed out for real: a protected page sends us back.
    await page.goto('/youth');
    await expect(page).toHaveURL(/\/login/);
  });
});
