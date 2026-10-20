def create_user(client, username="test-user", email="test@example.com"):
    return client.post("/users", json={"username": username, "email": email})


def test_health_check_reports_postgresql(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_user_crud(client):
    created = create_user(client)
    assert created.status_code == 201
    user = created.json()

    assert client.get(f"/users/{user['id']}").json() == user
    assert client.get("/users").json() == [user]

    updated = client.patch(f"/users/{user['id']}", json={"username": "renamed-user"})
    assert updated.status_code == 200
    assert updated.json()["username"] == "renamed-user"

    assert client.delete(f"/users/{user['id']}").status_code == 204
    assert client.get(f"/users/{user['id']}").status_code == 404


def test_task_crud_and_owner_filter(client):
    owner = create_user(client).json()
    other_owner = create_user(client, "other-user", "other@example.com").json()
    task = client.post(
        "/tasks",
        json={"title": "Test API", "description": "Check CRUD", "owner_id": owner["id"]},
    )
    assert task.status_code == 201
    task_data = task.json()
    assert task_data["completed"] is False

    other_task = client.post(
        "/tasks", json={"title": "Other task", "owner_id": other_owner["id"]}
    )
    assert other_task.status_code == 201

    assert client.get(f"/tasks/{task_data['id']}").json() == task_data
    assert [item["id"] for item in client.get("/tasks", params={"owner_id": owner["id"]}).json()] == [
        task_data["id"]
    ]

    updated = client.patch(f"/tasks/{task_data['id']}", json={"completed": True})
    assert updated.status_code == 200
    assert updated.json()["completed"] is True

    assert client.delete(f"/tasks/{task_data['id']}").status_code == 204
    assert client.get(f"/tasks/{task_data['id']}").status_code == 404


def test_task_rejects_unknown_owner(client):
    response = client.post("/tasks", json={"title": "Orphan", "owner_id": 999999})

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_deleting_user_unassigns_tasks(client):
    owner = create_user(client).json()
    task = client.post("/tasks", json={"title": "Keep this task", "owner_id": owner["id"]})
    task_id = task.json()["id"]

    assert client.delete(f"/users/{owner['id']}").status_code == 204
    response = client.get(f"/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json()["owner_id"] is None


def test_invalid_task_payload_is_rejected(client):
    response = client.post("/tasks", json={"title": ""})

    assert response.status_code == 422


def test_missing_task_returns_not_found(client):
    response = client.get("/tasks/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"