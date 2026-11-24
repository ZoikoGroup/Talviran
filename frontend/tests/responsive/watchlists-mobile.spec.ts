import { test, expect, type Page } from '@playwright/test'

/**
 * G09 remediation (UAT gap analysis): "Clipped mobile action and unproven
 * keyboard/screen-reader support."
 *
 * Root cause: WatchlistsPage.tsx's header row (title + "New Watchlist" /
 * "Watchlists Guide" buttons) used `flex items-start justify-between` with
 * no wrap/stacking, so at narrow viewports the "New Watchlist" button was
 * pushed off the right edge of the screen and was unreachable. Fixed to
 * `flex-col sm:flex-row` (matching the pattern already used elsewhere in
 * the same file) plus full-width stacked buttons below the `sm` breakpoint.
 *
 * This suite also covers the icon-only-button aria-label gap found in the
 * same audit item: WatchlistsPage.tsx (Delete Watchlist / Set Alert Rule /
 * Remove from watchlist) and TradingViewModal.tsx (Close chart) each had
 * only one aria-label in the whole file before this change.
 *
 * Requires a live backend at http://localhost:8000 (for real signup/
 * watchlist-seeding) and the frontend dev server at http://localhost:5173 -
 * see playwright.config.ts's `webServer`, which reuses an already-running
 * dev server instead of racing it for the port.
 */

const VIEWPORTS = [320, 360, 390, 768, 1280] as const

function freshEmail(): string {
  return `playwright-g09-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`
}

/** Signs up a brand-new account through the real UI and lands on the
 * Watchlists page, where the backend auto-seeds two preset watchlists
 * (`ensure_default_watchlists`) - so there is always at least one
 * non-default watchlist (reveals "Delete Watchlist") and at least one
 * item per list (reveals the per-row action buttons) without this test
 * having to create anything itself. */
async function signUpAndOpenWatchlists(page: Page): Promise<void> {
  const email = freshEmail()
  const password = 'Test-Password-1'

  await page.goto('/signup')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password').fill(password)
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Create account' }).click()

  // Successful signup redirects to '/'.
  await page.waitForURL((url) => url.pathname === '/', { timeout: 20_000 })

  await page.goto('/watchlists')
  await expect(page.getByRole('heading', { name: 'Watchlists & Market Portfolios' })).toBeVisible({
    timeout: 20_000,
  })
  // Wait for the seeded default watchlist's items to actually render before
  // any test starts asserting on them.
  await expect(page.getByText('UK 10Y Gilt', { exact: true })).toBeVisible({ timeout: 20_000 })
}

test.describe('G09 — Watchlists header mobile clipping', () => {
  test('New Watchlist and Watchlists Guide stay fully in-viewport at every width', async ({ page }) => {
    await signUpAndOpenWatchlists(page)

    const newWatchlistButton = page.getByRole('button', { name: 'New Watchlist' })
    const guideLink = page.getByRole('link', { name: 'Watchlists Guide' })

    for (const width of VIEWPORTS) {
      await page.setViewportSize({ width, height: 800 })
      // Let the layout settle after the resize before measuring.
      await page.waitForTimeout(100)

      await expect(newWatchlistButton).toBeVisible()
      await expect(guideLink).toBeVisible()

      const btnBox = await newWatchlistButton.boundingBox()
      const guideBox = await guideLink.boundingBox()
      expect(btnBox, `New Watchlist bounding box missing at ${width}px`).not.toBeNull()
      expect(guideBox, `Watchlists Guide bounding box missing at ${width}px`).not.toBeNull()

      // Fully within the viewport horizontally - not clipped off either edge.
      expect(btnBox!.x, `New Watchlist clipped on the left at ${width}px`).toBeGreaterThanOrEqual(0)
      expect(
        btnBox!.x + btnBox!.width,
        `New Watchlist clipped on the right at ${width}px (x=${btnBox!.x}, w=${btnBox!.width}, viewport=${width})`
      ).toBeLessThanOrEqual(width)

      expect(guideBox!.x, `Watchlists Guide clipped on the left at ${width}px`).toBeGreaterThanOrEqual(0)
      expect(
        guideBox!.x + guideBox!.width,
        `Watchlists Guide clipped on the right at ${width}px (x=${guideBox!.x}, w=${guideBox!.width}, viewport=${width})`
      ).toBeLessThanOrEqual(width)

      // No page-level horizontal scroll introduced by the header either.
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
      expect(scrollWidth, `Page requires horizontal scroll at ${width}px (scrollWidth=${scrollWidth})`).toBeLessThanOrEqual(
        width + 1 // +1px tolerance for sub-pixel rounding
      )
    }
  })

  test('both header buttons are reachable and actionable by keyboard', async ({ page }) => {
    await signUpAndOpenWatchlists(page)
    await page.setViewportSize({ width: 390, height: 800 })

    const newWatchlistButton = page.getByRole('button', { name: 'New Watchlist' })

    // Tab through the page from the top until focus actually lands on the
    // "New Watchlist" button, proving it is reachable via keyboard alone
    // (not just mouse) - bounded so a regression (focus trap / button
    // removed from the tab order) fails the test instead of hanging.
    await page.locator('body').click({ position: { x: 1, y: 1 } })
    let reached = false
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press('Tab')
      const isFocused = await newWatchlistButton.evaluate(
        (el) => el === document.activeElement
      )
      if (isFocused) {
        reached = true
        break
      }
    }
    expect(reached, 'New Watchlist button was never reached via Tab').toBe(true)
    await expect(newWatchlistButton).toBeFocused()

    // Actionable via Enter ...
    await page.keyboard.press('Enter')
    await expect(page.getByRole('heading', { name: 'Create New Watchlist' })).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('heading', { name: 'Create New Watchlist' })).not.toBeVisible()

    // ... and via Space.
    await newWatchlistButton.focus()
    await expect(newWatchlistButton).toBeFocused()
    await page.keyboard.press('Space')
    await expect(page.getByRole('heading', { name: 'Create New Watchlist' })).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()
  })

  test('icon-only buttons expose real, specific accessible names', async ({ page }) => {
    await signUpAndOpenWatchlists(page)

    // Pre-existing aria-label (sanity check this fix didn't regress it).
    await expect(page.getByRole('button', { name: 'Back' })).toBeVisible()

    // Per-row icon-only actions on the seeded default watchlist's items.
    await expect(page.getByRole('button', { name: 'Set alert rule for UK 10Y Gilt' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Remove UK 10Y Gilt from watchlist' })).toBeVisible()

    // The second seeded watchlist is not the default one, so its
    // icon-only "Delete Watchlist" button is rendered.
    await page.getByRole('button', { name: 'Major Indices & FX' }).click()
    await expect(
      page.getByRole('button', { name: 'Delete watchlist Major Indices & FX' })
    ).toBeVisible()

    // Opening a chart (TradingViewModal) exposes its own icon-only close
    // button, independent of whether the embedded chart widget itself
    // finishes loading.
    await page.locator('td', { hasText: 'S&P 500' }).first().click()
    const closeButton = page.getByRole('button', { name: 'Close chart' })
    await expect(closeButton).toBeVisible()
    await closeButton.click()
    await expect(closeButton).not.toBeVisible()
  })
})
