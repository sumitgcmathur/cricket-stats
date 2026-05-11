'use strict';

const { defineConfig } = require('@playwright/test');
const path = require('path');

/** When set (e.g. https://your-site.pages.dev), tests hit that origin and no local static server is started. */
const deployedBase = process.env.PLAYWRIGHT_BASE_URL || '';
const localBase = 'http://127.0.0.1:4173';

module.exports = defineConfig({
  testDir: path.join(__dirname, 'tests', 'e2e'),
  /** Must exceed longest waitForFunction in deployment smoke (120s). */
  timeout: 130_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: deployedBase || localBase,
    trace: 'on-first-retry',
  },
  webServer: deployedBase
    ? undefined
    : {
        command: 'npx serve . -l 4173',
        cwd: __dirname,
        url: `${localBase}/`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
