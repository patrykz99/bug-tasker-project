const { test, expect } = require("@playwright/test");

const portBase = Number(process.env.BUG_MODE_TEST_PORT_BASE || 18100);
const disabledApi = `http://127.0.0.1:${portBase}`;
const enabledApi = `http://127.0.0.1:${portBase + 1}`;
const authorizationEnabledApi = `http://127.0.0.1:${portBase + 2}`;
const delayThresholdMs = 400;

async function measureRequest(apiRequest, url) {
  const startedAt = performance.now();
  const response = await apiRequest.get(url);
  const elapsedMs = performance.now() - startedAt;
  return { response, elapsedMs };
}

function median(values) {
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.floor(ordered.length / 2)];
}

test("Bug Mode adds approximately 500 ms to database requests only when enabled", async ({
  request,
}) => {
  const disabledTimes = [];
  const enabledTimes = [];

  for (let sample = 0; sample < 3; sample += 1) {
    const disabled = await measureRequest(request, `${disabledApi}/healthz`);
    const enabled = await measureRequest(request, `${enabledApi}/healthz`);

    expect(disabled.response.status()).toBe(200);
    expect(enabled.response.status()).toBe(200);
    await expect(disabled.response.json()).resolves.toEqual({
      status: "ok",
      database: "connected",
    });
    await expect(enabled.response.json()).resolves.toEqual({
      status: "ok",
      database: "connected",
    });

    disabledTimes.push(disabled.elapsedMs);
    enabledTimes.push(enabled.elapsedMs);
  }

  expect(median(enabledTimes) - median(disabledTimes)).toBeGreaterThanOrEqual(
    delayThresholdMs
  );
});

test("a route that does not use the database does not get the Bug Mode delay", async ({
  request,
}) => {
  const rootResponse = await measureRequest(request, `${enabledApi}/`);
  const healthResponse = await measureRequest(request, `${enabledApi}/healthz`);

  expect(rootResponse.response.status()).toBe(200);
  await expect(rootResponse.response.json()).resolves.toEqual({
    status: "ok",
    message: "FastAPI is running!",
  });
  expect(healthResponse.response.status()).toBe(200);
  expect(healthResponse.elapsedMs - rootResponse.elapsedMs).toBeGreaterThanOrEqual(
    delayThresholdMs
  );
});

test("user and task CRUD continue to work with Bug Mode disabled and enabled", async ({
  request,
}) => {
  for (const [mode, apiUrl] of [
    ["disabled", disabledApi],
    ["enabled", enabledApi],
  ]) {
    const uniqueId = `${Date.now()}-${mode}`;
    let userId;
    let taskId;

    try {
      const createdUser = await request.post(`${apiUrl}/users`, {
        data: {
          username: `perf-${uniqueId}`,
          email: `perf-${uniqueId}@example.test`,
        },
      });
      expect(createdUser.status()).toBe(201);
      userId = (await createdUser.json()).id;

      const createdTask = await request.post(`${apiUrl}/tasks`, {
        data: { title: `Performance test ${uniqueId}`, owner_id: userId },
      });
      expect(createdTask.status()).toBe(201);
      taskId = (await createdTask.json()).id;

      const readTask = await request.get(`${apiUrl}/tasks/${taskId}`);
      expect(readTask.status()).toBe(200);
      expect(await readTask.json()).toMatchObject({
        title: `Performance test ${uniqueId}`,
        completed: false,
        owner_id: userId,
      });

      const updatedTask = await request.patch(`${apiUrl}/tasks/${taskId}`, {
        data: { completed: true },
      });
      expect(updatedTask.status()).toBe(200);
      expect(await updatedTask.json()).toMatchObject({
        id: taskId,
        completed: true,
      });

      const deletedTask = await request.delete(`${apiUrl}/tasks/${taskId}`);
      expect(deletedTask.status()).toBe(204);
      taskId = undefined;

      const deletedUser = await request.delete(`${apiUrl}/users/${userId}`);
      expect(deletedUser.status()).toBe(204);
      userId = undefined;
    } finally {
      if (taskId !== undefined) {
        const response = await request.delete(`${apiUrl}/tasks/${taskId}`);
        expect(response.status()).toBe(204);
      }
      if (userId !== undefined) {
        const response = await request.delete(`${apiUrl}/users/${userId}`);
        expect(response.status()).toBe(204);
      }
    }
  }
});

test("authorization Bug Mode blocks task endpoints only when enabled", async ({
  request,
}) => {
  const uniqueId = `${Date.now()}-authorization`;
  let userId;
  let taskId;

  try {
    const createdUser = await request.post(`${disabledApi}/users`, {
      data: {
        username: `auth-${uniqueId}`,
        email: `auth-${uniqueId}@example.test`,
      },
    });
    expect(createdUser.status()).toBe(201);
    userId = (await createdUser.json()).id;

    const createdTask = await request.post(`${disabledApi}/tasks`, {
      data: { title: `Authorization test ${uniqueId}`, owner_id: userId },
    });
    expect(createdTask.status()).toBe(201);
    taskId = (await createdTask.json()).id;

    const forbiddenResponses = [
      await request.get(`${authorizationEnabledApi}/tasks`),
      await request.get(`${authorizationEnabledApi}/tasks/${taskId}`),
      await request.post(`${authorizationEnabledApi}/tasks`, {
        data: { title: `Blocked task ${uniqueId}` },
      }),
      await request.patch(`${authorizationEnabledApi}/tasks/${taskId}`, {
        data: { completed: true },
      }),
      await request.delete(`${authorizationEnabledApi}/tasks/${taskId}`),
    ];

    for (const response of forbiddenResponses) {
      expect(response.status()).toBe(403);
      await expect(response.json()).resolves.toEqual({
        detail: "Access denied (simulated Bug Mode authorization failure)",
      });
    }

    const healthResponse = await request.get(`${authorizationEnabledApi}/healthz`);
    expect(healthResponse.status()).toBe(200);
    await expect(healthResponse.json()).resolves.toMatchObject({
      status: "ok",
      database: "connected",
    });

    const usersResponse = await request.get(`${authorizationEnabledApi}/users`);
    expect(usersResponse.status()).toBe(200);

    const taskAfterDeniedRequests = await request.get(`${disabledApi}/tasks/${taskId}`);
    expect(taskAfterDeniedRequests.status()).toBe(200);
    await expect(taskAfterDeniedRequests.json()).resolves.toMatchObject({
      id: taskId,
      completed: false,
    });
  } finally {
    if (taskId !== undefined) {
      const response = await request.delete(`${disabledApi}/tasks/${taskId}`);
      expect(response.status()).toBe(204);
    }
    if (userId !== undefined) {
      const response = await request.delete(`${disabledApi}/users/${userId}`);
      expect(response.status()).toBe(204);
    }
  }
});
