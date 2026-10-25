const os = require("node:os");
const path = require("node:path");
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.js",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  expect: {
    timeout: 5000,
  },
  reporter: [
    ["list"],
    [
      "allure-playwright",
      {
        resultsDir: "allure-results",
        detail: true,
      },
    ],
  ],
  outputDir: path.join(os.tmpdir(), `buggy-tasker-playwright-${process.pid}`),
  globalSetup: require.resolve("./tests/e2e/global-setup.js"),
});
