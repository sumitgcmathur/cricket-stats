'use strict';

const { test, expect } = require('@playwright/test');

/**
 * Collect hard failures (uncaught exceptions). Console errors from third-party
 * CDNs are ignored when they are network-only (fonts / chart).
 */
function attachSoftErrorListeners(page, bucket) {
  page.on('pageerror', (err) => {
    bucket.push(`pageerror: ${err.message}`);
  });
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const t = msg.text();
    if (/fonts\.googleapis|googleapis\.com\/css|ERR_ABORTED|Failed to load resource/i.test(t)) return;
    bucket.push(`console: ${t}`);
  });
}

/**
 * Wait until the index dashboard is in a terminal state (stats table, empty filter message, or boot error).
 * Avoids hanging the full test timeout when boot fails (e.g. invalid stats/index.json: `{\n<` merge markers).
 */
async function waitForIndexDashboardReady(page, { timeout = 120_000 } = {}) {
  await page.waitForFunction(
    () => {
      const root = document.getElementById('dash-content');
      if (!root) return false;
      const t = root.textContent || '';
      if (t.includes('Could not load data')) return true;
      if (t.includes('Error building view')) return true;
      if (root.querySelector('table')) return true;
      if (t.includes('No data for this filter')) return true;
      return false;
    },
    { timeout },
  );
  const kind = await page.evaluate(() => {
    const t = document.getElementById('dash-content')?.textContent || '';
    if (t.includes('Could not load data')) return 'boot';
    if (t.includes('Error building view')) return 'build';
    return 'ok';
  });
  if (kind === 'boot') {
    throw new Error(
      'Index boot failed ("Could not load data"). Ensure stats/index.json is valid JSON (no merge conflict markers) and stats/*.json exist.',
    );
  }
  if (kind === 'build') {
    throw new Error('Index failed while merging stats ("Error building view").');
  }
}

test.describe('post-deploy smoke', () => {
  test('home loads and shared filters script exposes t20EscapeHtml', async ({ page }) => {
    const errors = [];
    attachSoftErrorListeners(page, errors);

    await page.goto('/index.html');
    await expect(page.locator('.logo')).toContainText('T20');
    const hasEsc = await page.evaluate(() => typeof window.t20EscapeHtml === 'function');
    expect(hasEsc, 't20-filters must export t20EscapeHtml').toBe(true);
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('index: IPL only clears year range inputs', async ({ page }) => {
    const errors = [];
    attachSoftErrorListeners(page, errors);

    await page.goto('/index.html');
    await waitForIndexDashboardReady(page);

    await page.locator('#year-from').fill('2019');
    await page.locator('#year-to').fill('2024');
    await page.getByRole('button', { name: 'IPL only' }).click();

    await expect(page.locator('#year-from')).toHaveValue('');
    await expect(page.locator('#year-to')).toHaveValue('');
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('matches: IPL only clears year range', async ({ page }) => {
    const errors = [];
    attachSoftErrorListeners(page, errors);

    await page.goto('/matches.html');
    await page.waitForSelector('#matches-filter-tournaments input', { state: 'attached' });

    await page.locator('#matches-year-from').fill('2018');
    await page.locator('#matches-year-to').fill('2023');
    await page.getByRole('button', { name: 'IPL only' }).click();

    await expect(page.locator('#matches-year-from')).toHaveValue('');
    await expect(page.locator('#matches-year-to')).toHaveValue('');
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('team: IPL only clears year range', async ({ page }) => {
    const errors = [];
    attachSoftErrorListeners(page, errors);

    await page.goto('/team.html');
    /* <option> inside <select> is not "visible" to Playwright; wait for attached + populated. */
    await page.waitForSelector('#team-sel option:nth-child(2)', { state: 'attached', timeout: 60_000 });

    await page.locator('#team-year-from').fill('2017');
    await page.locator('#team-year-to').fill('2022');
    await page.getByRole('button', { name: 'IPL only' }).click();

    await expect(page.locator('#team-year-from')).toHaveValue('');
    await expect(page.locator('#team-year-to')).toHaveValue('');
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('player profile loads for sample IPL batter', async ({ page, baseURL }) => {
    const errors = [];
    attachSoftErrorListeners(page, errors);

    const name = 'V Kohli';
    /* serve defaults cleanUrls:true → redirects /player.html?foo → /player and drops ?foo (breaks boot). serve.json disables that. */
    const target = new URL('/player.html', baseURL);
    target.searchParams.set('name', name);
    await page.goto(target.toString(), { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#hero-name')).toContainText(name, { timeout: 60_000 });
    await page.getByRole('button', { name: 'IPL only' }).click();
    await expect(page.locator('#player-year-from')).toHaveValue('');
    await expect(page.locator('#player-year-to')).toHaveValue('');
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('stats index.json is reachable', async ({ request, baseURL }) => {
    const res = await request.get(new URL('/stats/index.json', baseURL).toString());
    expect(res.ok()).toBeTruthy();
    const j = await res.json();
    expect(Array.isArray(j.competitions)).toBeTruthy();
  });

  test('config.json is reachable and defines site scope', async ({ request, baseURL }) => {
    const res = await request.get(new URL('/config.json', baseURL).toString());
    expect(res.ok()).toBeTruthy();
    const j = await res.json();
    expect(Array.isArray(j.site.focusCompetitionCodes)).toBeTruthy();
    expect(Array.isArray(j.site.fallbackCompetitions)).toBeTruthy();
    expect(Array.isArray(j.cricsheet.competitions)).toBeTruthy();
  });

  test('index exposes t20MergeDatasets after merge script', async ({ page }) => {
    await page.goto('/index.html');
    await page.waitForFunction(() => typeof window.t20MergeDatasets === 'function', { timeout: 60_000 });
  });

  test('compare page shows head-to-head for two IPL batters', async ({ page, baseURL }) => {
    const errors = [];
    attachSoftErrorListeners(page, errors);

    const u = new URL('/compare.html', baseURL);
    u.searchParams.set('comps', 'ipl');
    u.searchParams.set('season', 'all');
    u.searchParams.set('p1', 'V Kohli');
    u.searchParams.set('p2', 'RG Sharma');

    await page.goto(u.toString(), { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.t20MergeDatasets === 'function', { timeout: 60_000 });

    await expect(page.locator('.card h2').filter({ hasText: 'Head-to-head' })).toBeVisible({
      timeout: 120_000,
    });
    await expect(page.locator('thead th').filter({ hasText: 'V Kohli' })).toBeVisible();
    await expect(page.locator('thead th').filter({ hasText: 'RG Sharma' })).toBeVisible();
    await expect(page.locator('.card h2').filter({ hasText: 'Runs (merged)' })).toBeVisible();

    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('compare page player fields offer search suggestions', async ({ page, baseURL }) => {
    const errors = [];
    attachSoftErrorListeners(page, errors);

    const u = new URL('/compare.html', baseURL);
    u.searchParams.set('comps', 'ipl');
    u.searchParams.set('season', 'all');

    await page.goto(u.toString(), { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.t20MergeDatasets === 'function', { timeout: 60_000 });

    await page.locator('#inp-p1').fill('kohl');
    await page.locator('#cmp-sug-p1 .cmp-sug-btn', { hasText: 'V Kohli' }).first().click({ timeout: 120_000 });

    await page.locator('#inp-p2').fill('sharma');
    await page.locator('#cmp-sug-p2 .cmp-sug-btn', { hasText: 'RG Sharma' }).first().click({ timeout: 120_000 });

    await page.getByRole('button', { name: 'Compare' }).click();

    await expect(page.locator('thead th').filter({ hasText: 'V Kohli' })).toBeVisible({ timeout: 120_000 });
    await expect(page.locator('thead th').filter({ hasText: 'RG Sharma' })).toBeVisible();

    expect(errors, errors.join('\n')).toEqual([]);
  });
});
