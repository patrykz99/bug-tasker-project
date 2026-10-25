const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const projectRoot = path.resolve(__dirname, "../..");
const backendPath = path.join(projectRoot, "backend");
const portBase = Number(process.env.BUG_MODE_TEST_PORT_BASE || 18100);
const startupTimeoutMs = 60000;

function getTestDatabaseUrl() {
  const databaseUrl = process.env.TEST_DATABASE_URL;
  if (!databaseUrl) {
    throw new Error(
      "Set TEST_DATABASE_URL to the dedicated PostgreSQL test database ending in _test."
    );
  }

  let parsedUrl;
  try {
    parsedUrl = new URL(databaseUrl);
  } catch {
    throw new Error("TEST_DATABASE_URL must be a valid PostgreSQL URL.");
  }

  if (!parsedUrl.protocol.startsWith("postgresql")) {
    throw new Error("TEST_DATABASE_URL must use PostgreSQL.");
  }
  if (!decodeURIComponent(parsedUrl.pathname).toLowerCase().endsWith("_test")) {
    throw new Error("TEST_DATABASE_URL must point to a database ending in _test.");
  }

  return databaseUrl;
}

function getPythonExecutable() {
  if (process.env.PYTHON_EXECUTABLE) {
    return process.env.PYTHON_EXECUTABLE;
  }

  const candidates = [
    path.join(backendPath, "venv", "Scripts", "python.exe"),
    path.join(backendPath, "venv", "bin", "python"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "python";
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForReady(server) {
  const deadline = Date.now() + startupTimeoutMs;

  while (Date.now() < deadline) {
    if (server.exited) {
      throw new Error(`Bug Mode ${server.mode} API exited during startup.
Exit code: ${server.exitCode}
Signal: ${server.exitSignal}
${server.logs}`);
    }

    try {
      const response = await fetch(`${server.url}/healthz`, {
        signal: AbortSignal.timeout(2000),
      });
      if (response.ok) {
        const body = await response.json();
        if (body.database === "connected") {
          return;
        }
      }
    } catch {
      // The API may need a few seconds to connect to PostgreSQL and start.
    }

    await delay(250);
  }

  throw new Error(
    `Bug Mode ${server.mode} API did not become ready within ${startupTimeoutMs} ms.\n${server.logs}`
  );
}

function startServer(mode, databaseUrl) {
  const port = portBase + (mode === "enabled" ? 1 : 0);
  const child = spawn(
    getPythonExecutable(),
    ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(port)],
    {
      cwd: backendPath,
      env: {
        ...process.env,
        DATABASE_URL: databaseUrl,
        ENABLE_BUG_MODE: mode === "enabled" ? "true" : "false",
        BUG_MODE_LOG: "true",
      },
      stdio: ["ignore", "pipe", "pipe"],
    }
  );

  const server = {
    child,
    mode,
    url: `http://127.0.0.1:${port}`,
    exited: false,
    exitCode: null,
    exitSignal: null,
    logs: "",
  };
  const appendLogs = (chunk) => {
    server.logs = `${server.logs}${chunk.toString()}`.slice(-12000);
  };

  child.stdout.on("data", appendLogs);
  child.stderr.on("data", appendLogs);
  child.on("error", (error) => {
    server.exited = true;
    server.logs += `\nFailed to start Python API: ${error.message}`;
  });
  child.on("exit", (code, signal) => {
    server.exited = true;
    server.exitCode = code;
    server.exitSignal = signal;
  });

  return server;
}

async function stopServer(server) {
  if (server.exited) {
    return;
  }

  const exited = new Promise((resolve) => server.child.once("exit", resolve));
  server.child.kill();
  await Promise.race([exited, delay(5000)]);

  if (!server.exited) {
    server.child.kill("SIGKILL");
    throw new Error(`Could not stop Bug Mode ${server.mode} API process.`);
  }
}

module.exports = async function globalSetup() {
  const databaseUrl = getTestDatabaseUrl();
  if (!Number.isInteger(portBase) || portBase < 1 || portBase > 65534) {
    throw new Error("BUG_MODE_TEST_PORT_BASE must be an integer between 1 and 65534.");
  }

  const servers = [];
  try {
    for (const mode of ["disabled", "enabled"]) {
      const server = startServer(mode, databaseUrl);
      servers.push(server);
      await waitForReady(server);
      console.log(`Bug Mode ${mode} API is ready at ${server.url}`);
    }
  } catch (error) {
    await Promise.all(servers.map(stopServer));
    throw error;
  }

  return async () => {
    await Promise.all(servers.map(stopServer));
  };
};
