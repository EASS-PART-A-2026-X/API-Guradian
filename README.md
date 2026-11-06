# API Guardian

API Guardian is a course project for managing and assessing API security. EX1 registers API projects and stores their metadata. A project has a name, an HTTP(S) base URL, and an optional description. The backend stores the URL without contacting it.

## Run locally

Install Python 3.12–3.14 and [uv](https://docs.astral.sh/uv/getting-started/installation/). From the repository root:

```sh
cd backend
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open the [interactive API docs](http://127.0.0.1:8000/docs). The backend creates its SQLite database and schema at startup. The default database path is `backend/data/api_guardian.db`. To change it, copy `.env.example` to `.env` in `backend/`, set `DATABASE_URL` to a SQLite file URL, then launch with `uv run --locked --env-file .env uvicorn app.main:app`. Relative database paths are resolved from the directory where you start Uvicorn.

## API

| Request | Behavior |
| --- | --- |
| `GET /health` | Check that the server responds. |
| `POST /projects` | Create a project and return it with status `201`. |
| `GET /projects` | List projects in ID order. |
| `GET /projects/{id}` | Read one project. |
| `PUT /projects/{id}` | Replace its editable fields. Omit `description` to clear it. |
| `DELETE /projects/{id}` | Delete a project and return an empty `204` response. |

Use this synthetic request body to create or replace a project:

```json
{
  "name": "Example API",
  "base_url": "https://api.example.com/v1",
  "description": "Synthetic project for the EX1 demo"
}
```

Invalid input returns `422`. Read, replace, and delete return `404` for a missing project. Base URLs support HTTP and HTTPS and exclude credentials, queries, and fragments.

## Run in Docker

Use Docker with Linux containers. Stop the local server if it is using port 8000. From the repository root:

```sh
docker build -t api-guardian-backend:ex1 backend
docker volume create api-guardian-ex1-data
docker run -d --name api-guardian-ex1 -p 127.0.0.1:8000:8000 -v api-guardian-ex1-data:/app/data api-guardian-backend:ex1
```

The image runs the server as user `10001`. The named volume holds `/app/data/api_guardian.db`. Check `GET /health` and create a project in the interactive docs. Note its ID, then replace the container using the same volume:

```sh
docker stop api-guardian-ex1
docker rm api-guardian-ex1
docker run -d --name api-guardian-ex1 -p 127.0.0.1:8000:8000 -v api-guardian-ex1-data:/app/data api-guardian-backend:ex1
```

Read the same ID using `GET /projects/{id}`. It should return the saved project. For a startup failure, inspect `docker logs api-guardian-ex1`.

## Tests

From `backend/`:

```sh
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The HTTP tests use isolated SQLite files. They check CRUD, validation, missing records, and whether creates, updates, and deletes survive closing and reopening the app against the same file.

## AI use

OpenAI Codex helped interpret the course requirements and drafted the backend, tests, Dockerfile, and documentation. Verification used pytest, Ruff, and HTTP requests against a running local backend. The Docker build and named-volume check require a Docker engine.
