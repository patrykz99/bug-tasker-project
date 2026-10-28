# Buggy Tasker API - BE + QA Automation Project

Project is ceating to showcase modern techniques for API test automation, continerization (Docker), and CI/CD processes.

The main goal of the project is to build a backend application with a dedicated "Bug Mode" for intentionally simulating regressions detected by automated tests. The currently implemented scenarios simulate database latency and authorization failures; security-vulnerability scenarios are not implemented yet.

---

## 🛠️ Planned Tech Stack
| Layer | Technology | Role in the project |
|---|---|---|
| **Backend** | FastAPI (Python) | Lightweight and fast API backend with Swagger documentation |
| **Database** | PostgreSQL | Relational database for storing tasks and users |
| **Containerization** | Docker & Docker Compose | Isolating the database and application in separate containers |
| **E2E / API Tests** | Playwright APIRequestContext (JavaScript) | Automated API regression and performance tests |
| **CI/CD** | GitHub Actions | Automatically running tests on every `git push` |

---


## Run Locally

Docker Compose starts PostgreSQL and the FastAPI backend. Development defaults are provided in `docker-compose.yml`; copy `.env.example` to `.env` to override the database credentials.

```sh
docker compose up --build
```

The API is available at `http://localhost:8000`. Interactive API documentation is at `http://localhost:8000/docs`.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/healthz` | Check API and PostgreSQL connectivity |
| `POST`, `GET` | `/users` | Create and list users |
| `GET`, `PATCH`, `DELETE` | `/users/{user_id}` | Read, update, and delete a user |
| `POST`, `GET` | `/tasks` | Create and list tasks; list supports `owner_id`, `offset`, and `limit` filters |
| `GET`, `PATCH`, `DELETE` | `/tasks/{task_id}` | Read, update, and delete a task |

Tasks may optionally be assigned to a user. Deleting an assigned user leaves the task in place and clears its owner.

## Bug Mode

Bug Mode is opt-in and disabled by default. It currently supports two independent simulations:

- **Performance regression:** requests that use the database perform an additional `SELECT 1` on their existing database session and wait for 500 ms before continuing. This increases request latency without changing the API response or stored data.
- **Authorization failure:** all `/tasks` endpoints return `403 Forbidden` with a simulated authorization error. The `/healthz` and `/users` endpoints remain available. This is a deterministic failure simulation, not real authentication or authorization.

Configure the modes with these environment variables:

| Variable | Default | Description |
|---|---|---|
| `ENABLE_BUG_MODE` | `false` | Enables the extra database query and 500 ms delay when set to `true` (case-insensitive). |
| `BUG_MODE_LOG` | `false` | Writes a warning with elapsed time for each performance regression when set to `true`. This flag does not enable Bug Mode by itself. |
| `ENABLE_AUTH_BUG_MODE` | `false` | Makes all `/tasks` endpoints return the simulated `403 Forbidden` response when set to `true` (case-insensitive). Independent of the performance mode. |

Set these values in `.env` before starting Docker Compose, or pass them directly to the application process. For example, to enable the performance regression and its log:

```dotenv
ENABLE_BUG_MODE=true
BUG_MODE_LOG=true
```

To simulate an authorization failure for task requests instead:

```dotenv
ENABLE_AUTH_BUG_MODE=true
```

The performance and authorization modes can be enabled independently or together. Restart the application after changing environment variables. If the performance regression query fails, the exception is logged and the session is rolled back before the request continues without the injected delay; the endpoint's own database operation can still fail normally. Keep all Bug Modes disabled in production.

## Run API Tests

The pytest API suite uses PostgreSQL and refuses to run unless `TEST_DATABASE_URL` points to a database whose name ends in `_test`. It clears the `users` and `tasks` tables between tests, so do not point it at your development database.

Create a dedicated test database in the Compose PostgreSQL container once:

```powershell
docker compose exec dev-db createdb -U buggytasker buggytasker_test
```

Install the backend dependencies and run tests from the repository root. Update the connection string if you changed the Compose credentials:

```powershell
python -m pip install -r backend/requirments.txt
$env:TEST_DATABASE_URL = "postgresql://buggytasker:buggytasker_dev_password@localhost:5432/buggytasker_test"
python -m pytest backend/tests -v
```

The Bug Mode tests cover flag parsing, the additional query and delay, optional logging, graceful handling of a failed regression query, and preservation of user/task API behavior when the mode is enabled.

### Playwright Bug Mode API tests

The Playwright suite starts three local API processes against the dedicated `*_test` database: one with performance Bug Mode disabled, one with performance Bug Mode enabled, and one with authorization Bug Mode enabled. It verifies the performance response and latency difference, confirms routes without database access are not delayed, exercises user/task CRUD with performance mode both ways, and checks that authorization mode returns `403` for all task endpoints while health and user endpoints remain available. It uses Playwright's API request client and does not require browser installation.

#### Run the tests in both modes

You do **not** need to switch Bug Mode flags in `.env` or recreate the Compose `web` container for this suite. The test setup starts three temporary local API processes and sets their flags independently:

| Test API | `ENABLE_BUG_MODE` | `ENABLE_AUTH_BUG_MODE` | URL |
|---|---:|---:|---|
| Performance disabled | `false` | `false` | `http://127.0.0.1:18100` |
| Performance enabled | `true` | `false` | `http://127.0.0.1:18101` |
| Authorization enabled | `false` | `true` | `http://127.0.0.1:18102` |

The performance checks compare requests to the first two processes and confirm the enabled process adds at least 400 ms. They also check that `/` (which does not use the database) is not delayed and that user/task CRUD works in both performance modes. Authorization tests verify all `/tasks` methods return the simulated `403` only on the authorization-enabled process, while `/healthz` and `/users` remain available. They also confirm a denied task update does not modify the stored task and that the performance-disabled process can still access it. The temporary API processes are stopped after the suite finishes.

Before running it:

1. Start the PostgreSQL Compose service and make sure the dedicated `buggytasker_test` database exists. See the test database setup instructions in [Run API Tests](#run-api-tests) above.
2. Install backend dependencies into `backend/venv` if they are not installed yet. The test runner uses `backend/venv/Scripts/python.exe` on Windows by default.
3. Install the Node test dependency once with `npm ci`.
4. Set `TEST_DATABASE_URL` in the terminal where you will run the tests. It must point to `buggytasker_test`, **never** to the development database.

PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql://buggytasker:<password>@localhost:5432/buggytasker_test"
npm run test:bug-mode
```

CMD:

```cmd
set "TEST_DATABASE_URL=postgresql://buggytasker:<password>@localhost:5432/buggytasker_test"
npm run test:bug-mode
```

Replace `<password>` with the local `POSTGRES_PASSWORD` from `.env`. In CMD, the variable applies only to the current terminal session. The test runner validates that the URL uses PostgreSQL and its database name ends in `_test`, then uses it for all temporary API processes. If the default ports `18100`-`18102` are occupied, set `BUG_MODE_TEST_PORT_BASE` to another available base port. If Python is not at `backend/venv`, set `PYTHON_EXECUTABLE` to the Python executable that has the backend requirements installed. The tests delete the user/task records they create; they do not clear the whole test database.

#### Allure reports

Playwright writes Allure result files to `allure-results/` while keeping the normal console output. After a test run, generate a browsable HTML report with:

```powershell
npm run report:allure
npm run report:allure:open
```

The generated report is in `allure-report/`; `report:allure:open` opens it in a local browser. Generating the report requires Java and may be run even if some tests failed, so their results can still be inspected. Both generated directories are ignored by Git and should not be committed. To generate a fresh report, run the Playwright test command again first so `allure-results/` contains the latest run.

## TO_DO

- [✅] Add Bug Mode scenarios for authorization failures, with explicit opt-in configuration and safe defaults.
- [ ] Add Bug Mode security-vulnerability scenarios, isolated to a local/test environment and disabled by default.
- [✅] Add automated tests for the authorization Bug Mode scenarios, including enabled and disabled behavior.
- [ ] Add automated tests for the security Bug Mode scenarios, including enabled and disabled behavior and verification that the normal application path remains unaffected.
- [ ] Set up CI with GitHub Actions to run the Python test suite and Playwright performance tests on pushes and pull requests. Provision PostgreSQL and the dedicated test database in CI, configure test-only credentials, and report test failures clearly.