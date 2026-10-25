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
| **E2E / API Tests** | Playwright (TypeScript) | Automation of regression, performance, and security tests |
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