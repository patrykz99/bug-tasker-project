const { test, expect } = require("@playwright/test");

const portBase = Number(process.env.BUG_MODE_TEST_PORT_BASE || 18100);
const disabledApi = `http://127.0.0.1:${portBase}`;
const securityEnabledApi = `http://127.0.0.1:${portBase + 2}`;

test("Security Bug Mode omits only X-Content-Type-Options", async ({ request }) => {
  for (const path of ["/", "/healthz", "/users", "/tasks"]) {
    const safeResponse = await request.get(`${disabledApi}${path}`);
    const simulatedResponse = await request.get(`${securityEnabledApi}${path}`);

    expect(safeResponse.status()).toBe(simulatedResponse.status());
    expect(await safeResponse.body()).toEqual(await simulatedResponse.body());
    expect(safeResponse.headers()["x-content-type-options"]).toBe("nosniff");
    expect(simulatedResponse.headers()["x-content-type-options"]).toBeUndefined();
  }

  const safeNotFound = await request.get(`${disabledApi}/missing`);
  const simulatedNotFound = await request.get(`${securityEnabledApi}/missing`);
  expect(safeNotFound.status()).toBe(404);
  expect(simulatedNotFound.status()).toBe(404);
  expect(safeNotFound.headers()["x-content-type-options"]).toBe("nosniff");
  expect(simulatedNotFound.headers()["x-content-type-options"]).toBeUndefined();
});
