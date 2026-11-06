import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine

from app.main import create_app

PROJECT = {
    "name": "Demo API",
    "base_url": "https://api.example.com/v1",
    "description": "Synthetic project",
}


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'data' / 'test.db').as_posix()}"


@pytest.fixture
def client(database_url):
    with TestClient(create_app(database_url)) as test_client:
        yield test_client


def test_project_lifecycle(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/projects").json() == []

    created = client.post("/projects", json=PROJECT)
    assert created.status_code == 201
    project_id = created.json()["id"]
    path = f"/projects/{project_id}"
    assert created.json() == {"id": project_id, **PROJECT}
    assert client.get(path).json() == created.json()
    assert client.get("/projects").json() == [created.json()]

    updated = client.put(
        path, json={"name": "  Updated API  ", "base_url": PROJECT["base_url"]}
    )
    assert updated.status_code == 200
    assert updated.json() == {
        "id": project_id,
        "name": "Updated API",
        "base_url": PROJECT["base_url"],
        "description": None,
    }
    assert client.get(path).json() == updated.json()

    deleted = client.delete(path)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(path).status_code == 404
    assert client.get("/projects").json() == []


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"name": "   "},
        {"name": None},
        {"name": "a" * 101},
        {"description": "a" * 1001},
        {"base_url": "not-a-url"},
        {"base_url": "ftp://example.com"},
        {"base_url": "https://user:password@example.com"},
        {"base_url": "https://example.com/?debug=true"},
        {"base_url": "https://example.com/#fragment"},
        {"id": 42},
    ],
)
def test_invalid_create_does_not_save(client, invalid_fields):
    response = client.post("/projects", json={**PROJECT, **invalid_fields})
    assert response.status_code == 422
    assert client.get("/projects").json() == []


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_url_validation_does_not_echo_credentials(client, method):
    path = "/projects"
    if method == "PUT":
        project = client.post(path, json=PROJECT).json()
        path = f"{path}/{project['id']}"

    secret = "synthetic-secret-token"
    response = client.request(
        method, path, json={**PROJECT, "base_url": f"https://user:{secret}@example.com"}
    )
    assert response.status_code == 422
    assert secret not in response.text
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "base_url"]
    assert "must not include credentials" in error["msg"]


def test_invalid_update_leaves_project_intact(client):
    project = client.post("/projects", json=PROJECT).json()
    path = f"/projects/{project['id']}"
    assert client.put(path, json={"name": "Missing base URL"}).status_code == 422
    assert client.get(path).json() == project


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_missing_project_returns_404(client, method):
    body = {"json": PROJECT} if method == "PUT" else {}
    response = client.request(method, "/projects/999", **body)
    assert response.status_code == 404
    assert response.json() == {"detail": "API project not found"}


@pytest.mark.parametrize("project_id", ["-1", "abc", str(2**63)])
def test_invalid_project_id_returns_422(client, project_id):
    assert client.get(f"/projects/{project_id}").status_code == 422


def test_writes_survive_restarting_the_app(database_url):
    with TestClient(create_app(database_url)) as first:
        retained = first.post("/projects", json=PROJECT)
        removed = first.post("/projects", json=PROJECT)
        assert retained.status_code == removed.status_code == 201
        retained_path = f"/projects/{retained.json()['id']}"
        removed_path = f"/projects/{removed.json()['id']}"
        updated = first.put(retained_path, json={**PROJECT, "name": "Persisted API"})
        assert updated.status_code == 200
        assert first.delete(removed_path).status_code == 204

    with TestClient(create_app(database_url)) as restarted:
        assert restarted.get(retained_path).json() == updated.json()
        assert restarted.get(removed_path).status_code == 404
        assert restarted.get("/projects").json() == [updated.json()]
        replacement = restarted.post("/projects", json=PROJECT)
        assert replacement.status_code == 201
        assert replacement.json()["id"] > removed.json()["id"]
        assert restarted.get(removed_path).status_code == 404


def test_legacy_database_preserves_records_and_stops_reusing_ids(tmp_path):
    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE api_projects (id INTEGER NOT NULL PRIMARY KEY, "
            "name VARCHAR NOT NULL, base_url VARCHAR NOT NULL, description VARCHAR)"
        )
        connection.exec_driver_sql(
            "INSERT INTO api_projects (id, name, base_url, description) VALUES (?, ?, ?, ?)",
            (7, PROJECT["name"], PROJECT["base_url"], PROJECT["description"]),
        )
    engine.dispose()

    with TestClient(create_app(url)) as client:
        assert client.get("/projects/7").json() == {"id": 7, **PROJECT}
        assert client.delete("/projects/7").status_code == 204

    with TestClient(create_app(url)) as restarted:
        created = restarted.post("/projects", json=PROJECT)
        assert created.status_code == 201
        assert created.json()["id"] > 7
        assert restarted.get("/projects/7").status_code == 404
