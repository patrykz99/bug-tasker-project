# Buggy Tasker API - BE + QA Automation Project

Project is ceating to showcase modern techniques for API test automation, continerization (Docker), and CI/CD processes.

The main goal of the project is to build a backend application with a dedicated "Bug Mode" for intentionally simulating regressions detected by automated tests. The currently implemented scenario adds database work and latency; authorization and security-vulnerability scenarios are not implemented yet.

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

Bug Mode is an opt-in performance-regression simulation for requests that use the database, including health checks and the user and task endpoints. When enabled, each such request performs an additional `SELECT 1` on its existing database session and waits for 500 ms before continuing. This intentionally increases request latency without changing the API response or stored data. It is disabled by default.

Configure the feature with these environment variables:

| Variable | Default | Description |
|---|---|---|
| `ENABLE_BUG_MODE` | `false` | Enables the extra database query and 500 ms delay when set to `true` (case-insensitive). |
| `BUG_MODE_LOG` | `false` | Writes a warning with elapsed time for each enabled regression when set to `true`. This flag does not enable Bug Mode by itself. |

Set these values in `.env` before starting Docker Compose, or pass them directly to the application process. For example, to enable the regression and its log:

```dotenv
ENABLE_BUG_MODE=true
BUG_MODE_LOG=true
```

Restart the application after changing environment variables. If the regression query fails, the exception is logged and the session is rolled back before the request continues without the injected delay; the endpoint's own database operation can still fail normally. Keep Bug Mode disabled in production.

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

### Playwright performance-mode API tests

The Playwright suite starts two local API processes against the dedicated `*_test` database: one with Bug Mode disabled and one enabled. It verifies the response and latency difference, confirms routes without database access are not delayed, and exercises user/task CRUD in both modes. It uses Playwright's API request client and does not require browser installation.

#### Run the tests in both modes

You do **not** need to switch `ENABLE_BUG_MODE` in `.env` or recreate the Compose `web` container for this suite. The test setup starts two temporary local API processes and sets their flags independently:

| Test API | `ENABLE_BUG_MODE` | URL |
|---|---:|---|
| Disabled | `false` | `http://127.0.0.1:18100` |
| Enabled | `true` | `http://127.0.0.1:18101` |

The test suite sends requests to both processes and checks that database-backed requests return the same successful responses, while the enabled process adds at least 400 ms compared with the disabled process. It also checks that `/` (which does not use the database) is not delayed and that user/task CRUD works in both modes. The temporary API processes are stopped after the suite finishes.

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

Replace `<password>` with the local `POSTGRES_PASSWORD` from `.env`. In CMD, the variable applies only to the current terminal session. The test runner validates that the URL uses PostgreSQL and its database name ends in `_test`, then uses it for both temporary API processes. If the default ports `18100` and `18101` are occupied, set `BUG_MODE_TEST_PORT_BASE` to another available base port. If Python is not at `backend/venv`, set `PYTHON_EXECUTABLE` to the Python executable that has the backend requirements installed. The tests delete the user/task records they create; they do not clear the whole test database.

#### Allure reports

Playwright writes Allure result files to `allure-results/` while keeping the normal console output. After a test run, generate a browsable HTML report with:

```powershell
npm run report:allure
npm run report:allure:open
```

The generated report is in `allure-report/`; `report:allure:open` opens it in a local browser. Generating the report requires Java and may be run even if some tests failed, so their results can still be inspected. Both generated directories are ignored by Git and should not be committed. To generate a fresh report, run the Playwright test command again first so `allure-results/` contains the latest run.

## TO_DO

- [ ] Add Bug Mode scenarios for authorization failures, with explicit opt-in configuration and safe defaults.
- [ ] Add Bug Mode security-vulnerability scenarios, isolated to a local/test environment and disabled by default.
- [ ] Add automated tests for the authorization Bug Mode scenarios, including enabled and disabled behavior.
- [ ] Add automated tests for the security Bug Mode scenarios, including enabled and disabled behavior and verification that the normal application path remains unaffected.
- [ ] Set up CI with GitHub Actions to run the Python test suite and Playwright performance tests on pushes and pull requests. Provision PostgreSQL and the dedicated test database in CI, configure test-only credentials, and report test failures clearly.