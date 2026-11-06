import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from sqlalchemy import delete, update
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app.projects import ApiProject, ProjectInput, ProjectRead

DEFAULT_DATABASE_URL = "sqlite:///data/api_guardian.db"
ProjectId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def initialize_database(engine: Engine) -> None:
    with engine.begin() as connection:
        # SQLite needs an explicit transaction for atomic DDL. The write lock
        # also prevents another startup from migrating the same table.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        schema = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'api_projects'"
        ).scalar_one_or_none()
        if schema is None or "AUTOINCREMENT" in schema.upper():
            SQLModel.metadata.create_all(connection)
            return

        connection.exec_driver_sql(
            "ALTER TABLE api_projects RENAME TO api_projects_old"
        )
        SQLModel.metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO api_projects (id, name, base_url, description) "
            "SELECT id, name, base_url, description FROM api_projects_old"
        )
        connection.exec_driver_sql("DROP TABLE api_projects_old")


def create_app(database_url: str | None = None) -> FastAPI:
    engine = create_engine(
        database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        connect_args={"check_same_thread": False},
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        FilePath(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
        try:
            initialize_database(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="API Guardian", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def redact_base_url_errors(
        request: Request, exc: RequestValidationError
    ) -> Response:
        errors = [error.copy() for error in exc.errors()]
        for error in errors:
            location = tuple(error["loc"])
            if location == ("body",) or location[:2] == ("body", "base_url"):
                error.pop("input", None)
        return await request_validation_exception_handler(
            request, RequestValidationError(errors)
        )

    def get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    ProjectSession = Annotated[Session, Depends(get_session)]

    def project_not_found() -> HTTPException:
        return HTTPException(status.HTTP_404_NOT_FOUND, "API project not found")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/projects", status_code=status.HTTP_201_CREATED)
    def create_project(body: ProjectInput, session: ProjectSession) -> ProjectRead:
        project = ApiProject.model_validate(body.model_dump(mode="json"))
        session.add(project)
        session.flush()
        result = ProjectRead.model_validate(project)
        session.commit()
        return result

    @app.get("/projects", response_model=list[ProjectRead])
    def list_projects(session: ProjectSession) -> list[ApiProject]:
        return list(session.exec(select(ApiProject).order_by(ApiProject.id)).all())

    @app.get("/projects/{project_id}", response_model=ProjectRead)
    def read_project(project_id: ProjectId, session: ProjectSession) -> ApiProject:
        project = session.get(ApiProject, project_id)
        if project is None:
            raise project_not_found()
        return project

    @app.put("/projects/{project_id}")
    def replace_project(
        project_id: ProjectId, body: ProjectInput, session: ProjectSession
    ) -> ProjectRead:
        statement = (
            update(ApiProject)
            .where(ApiProject.id == project_id)
            .values(**body.model_dump(mode="json"))
            .returning(ApiProject)
        )
        project = session.exec(statement).scalar_one_or_none()
        if project is None:
            raise project_not_found()
        result = ProjectRead.model_validate(project)
        session.commit()
        return result

    @app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_project(project_id: ProjectId, session: ProjectSession) -> Response:
        statement = (
            delete(ApiProject)
            .where(ApiProject.id == project_id)
            .returning(ApiProject.id)
        )
        if session.exec(statement).scalar_one_or_none() is None:
            raise project_not_found()
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app()
