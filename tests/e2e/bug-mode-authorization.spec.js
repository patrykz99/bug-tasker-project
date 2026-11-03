const { test, expect } = require("@playwright/test");

const portBase = Number(process.env.BUG_MODE_TEST_PORT_BASE || 18100);
const disabledApi = `http://127.0.0.1:${portBase}`;
const authorizationEnabledApi = `http://127.0.0.1:${portBase + 3}`;

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
