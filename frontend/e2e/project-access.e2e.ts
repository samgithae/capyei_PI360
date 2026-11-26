import { expect, test } from '@playwright/test';
import { expectAccessible, signIn } from './support';

/** NEW-057: an administrator gives a staff member project access. Synthetic seed accounts only. */
test.describe('project access for staff', () => {
  test('an administrator assigns a project and the summary and count follow', async ({
    page,
  }) => {
    await signIn(page, 'admin');
    await page.goto('/administration/users');
    const row = page.getByRole('row').filter({ hasText: 'dev.officer' });
    await row.getByRole('button', { name: 'Project access' }).click();

    const summary = page.getByTestId('project-summary');
    await expect(summary).toContainText('No project is assigned');
    await page.getByLabel(/Project 1/).check();
    await expect(summary).toContainText('Assigned to 1 project: Project 1');
    await expectAccessible(page, 'the Project access panel');

    await page.getByRole('button', { name: 'Save project access' }).click();
    await expect(page.getByTestId('project-summary')).toHaveCount(0);

    // Saved for real: reopen, and the project is still ticked.
    await row.getByRole('button', { name: 'Project access' }).click();
    await expect(page.getByTestId('project-summary')).toContainText(
      'Assigned to 1 project: Project 1',
    );
    // Put it back so later tests start from the seed.
    await page.getByLabel(/Project 1/).uncheck();
    await page.getByRole('button', { name: 'Save project access' }).click();
    await expect(page.getByTestId('project-summary')).toHaveCount(0);
  });

  test('on a phone the panel fits the screen and can be used', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await signIn(page, 'admin');
    await page.goto('/administration/users');
    await page
      .getByRole('row')
      .filter({ hasText: 'dev.officer' })
      .getByRole('button', { name: 'Project access' })
      .click();
    const save = page.getByRole('button', { name: 'Save project access' });
    await save.scrollIntoViewIfNeeded();
    await expect(save).toBeVisible();
    const box = await save.boundingBox();
    expect(box && box.x >= 0 && box.x + box.width <= 375).toBe(true);
    // No sideways scrolling of the page itself.
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    await expectAccessible(page, 'the Project access panel on a phone');
  });
});
