import logging

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend import main


@pytest.fixture
def bug_mode_enabled(monkeypatch):
    monkeypatch.setattr(main, "BUG_MODE_ENABLED", True)
    monkeypatch.setattr(main, "BUG_MODE_LOG", True)
    monkeypatch.setattr(main.time, "sleep", lambda _: None)


class TestBugModePerformanceRegression:
    def test_health_check_with_bug_mode_enabled(self, client, bug_mode_enabled):
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "connected"}

    def test_user_crud_still_works_with_bug_mode(self, client, bug_mode_enabled):
        response = client.post(
            "/users",
            json={"username": "test-user", "email": "test@example.com"},
        )
        assert response.status_code == 201
        user_id = response.json()["id"]

        response = client.get(f"/users/{user_id}")
        assert response.status_code == 200
        assert response.json()["username"] == "test-user"

        response = client.get("/users")
        assert response.status_code == 200
        assert len(response.json()) >= 1

        response = client.patch(
            f"/users/{user_id}",
            json={"username": "renamed-test-user"},
        )
        assert response.status_code == 200
        assert response.json()["username"] == "renamed-test-user"

        assert client.delete(f"/users/{user_id}").status_code == 204
        assert client.get(f"/users/{user_id}").status_code == 404

    def test_task_crud_still_works_with_bug_mode(self, client, bug_mode_enabled):
        user_response = client.post(
            "/users",
            json={"username": "task-owner", "email": "owner@example.com"},
        )
        assert user_response.status_code == 201
        owner_id = user_response.json()["id"]

        task_response = client.post(
            "/tasks",
            json={
                "title": "Test Task",
                "description": "Test description",
                "owner_id": owner_id,
            },
        )
        assert task_response.status_code == 201
        task_id = task_response.json()["id"]

        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Test Task"
        assert response.json()["completed"] is False

        response = client.get("/tasks")
        assert response.status_code == 200
        assert len(response.json()) >= 1

        response = client.get("/tasks", params={"owner_id": owner_id})
        assert response.status_code == 200
        assert len(response.json()) >= 1

        response = client.patch(
            f"/tasks/{task_id}",
            json={"completed": True},
        )
        assert response.status_code == 200
        assert response.json()["completed"] is True

        assert client.delete(f"/tasks/{task_id}").status_code == 204
        assert client.get(f"/tasks/{task_id}").status_code == 404


class TestBugModeEnvironmentVariables:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (None, False),
            ("false", False),
            ("true", True),
            ("TRUE", True),
            (" true ", True),
        ],
    )
    def test_flag_defaults_to_disabled_unless_true(self, value, expected):
        assert main._is_enabled(value) is expected


class TestBugModeFunctionality:
    def test_bug_mode_logging_active(self, client, bug_mode_enabled, caplog):
        caplog.set_level(logging.WARNING, logger=main.__name__)
        response = client.post(
            "/users",
            json={"username": "log-test-user", "email": "log@example.com"},
        )

        assert response.status_code == 201
        assert "BUG MODE: added database round trip" in caplog.text

    def test_disabled_bug_mode_skips_database_query(self, monkeypatch):
        monkeypatch.setattr(main, "BUG_MODE_ENABLED", False)

        class UnexpectedSession:
            def execute(self, _statement):
                pytest.fail("Bug Mode must not query the database when disabled")

        main.performance_regression_workaround(UnexpectedSession())

    def test_enabled_bug_mode_runs_query_and_delay(self, monkeypatch, caplog):
        calls = []

        class FakeSession:
            def execute(self, statement):
                calls.append(statement)

        sleeps = []
        monkeypatch.setattr(main, "BUG_MODE_ENABLED", True)
        monkeypatch.setattr(main, "BUG_MODE_LOG", False)
        monkeypatch.setattr(main.time, "sleep", sleeps.append)

        main.performance_regression_workaround(FakeSession())

        assert len(calls) == 1
        assert sleeps == [main.BUG_MODE_DELAY_SECONDS]
        assert "BUG MODE" not in caplog.text

    def test_database_error_is_logged_without_masking_request(
        self, monkeypatch, caplog
    ):
        class FailingSession:
            rolled_back = False

            def execute(self, _statement):
                raise SQLAlchemyError("query failed")

            def rollback(self):
                self.rolled_back = True

        monkeypatch.setattr(main, "BUG_MODE_ENABLED", True)
        monkeypatch.setattr(main, "BUG_MODE_LOG", False)
        caplog.set_level(logging.ERROR, logger=main.__name__)

        session = FailingSession()
        main.performance_regression_workaround(session)

        assert session.rolled_back
        assert "Bug Mode performance regression query failed" in caplog.text


class TestAuthorizationBugMode:
    def test_task_endpoints_return_forbidden_when_enabled(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(main, "AUTH_BUG_MODE_ENABLED", False)
        owner_response = client.post(
            "/users",
            json={"username": "auth-mode-owner", "email": "auth-mode@example.com"},
        )
        assert owner_response.status_code == 201
        owner_id = owner_response.json()["id"]

        created_task = client.post(
            "/tasks", json={"title": "Protected task", "owner_id": owner_id}
        )
        assert created_task.status_code == 201
        task_id = created_task.json()["id"]

        monkeypatch.setattr(main, "AUTH_BUG_MODE_ENABLED", True)
        requests = [
            client.get("/tasks"),
            client.get(f"/tasks/{task_id}"),
            client.post("/tasks", json={"title": "Blocked task"}),
            client.patch(f"/tasks/{task_id}", json={"completed": True}),
            client.delete(f"/tasks/{task_id}"),
        ]

        for response in requests:
            assert response.status_code == 403
            assert response.json() == {
                "detail": "Access denied (simulated Bug Mode authorization failure)"
            }

        monkeypatch.setattr(main, "AUTH_BUG_MODE_ENABLED", False)
        task_after_requests = client.get(f"/tasks/{task_id}")
        assert task_after_requests.status_code == 200
        assert task_after_requests.json()["completed"] is False
        assert len(client.get("/tasks").json()) == 1

    def test_non_task_endpoints_remain_available_when_enabled(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(main, "AUTH_BUG_MODE_ENABLED", True)

        health_response = client.get("/healthz")
        users_response = client.get("/users")

        assert health_response.status_code == 200
        assert health_response.json() == {
            "status": "ok",
            "database": "connected",
        }
        assert users_response.status_code == 200
        assert client.post(
            "/users",
            json={"username": "still-available", "email": "still@example.com"},
        ).status_code == 201

    def test_task_endpoints_work_when_disabled(self, client, monkeypatch):
        monkeypatch.setattr(main, "AUTH_BUG_MODE_ENABLED", False)

        response = client.get("/tasks")

        assert response.status_code == 200
        assert response.json() == []


class TestBugModeRaceConditions:
    def test_task_delete_race_condition(self, client, bug_mode_enabled):
        user_response = client.post(
            "/users",
            json={"username": "race-owner", "email": "race@example.com"},
        )
        owner_id = user_response.json()["id"]

        task_response = client.post(
            "/tasks", json={"title": "Race Task", "owner_id": owner_id}
        )
        task_id = task_response.json()["id"]

        assert client.delete(f"/tasks/{task_id}").status_code == 204
        assert client.delete(f"/tasks/{task_id}").status_code == 404
