import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Response, status
from sqlalchemy import delete, update
from sqlmodel import Session, SQLModel, create_engine, select

from app.projects import ApiProject, ProjectInput, ProjectRead

DEFAULT_DATABASE_URL = "sqlite:///data/api_guardian.db"
ProjectId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def create_app(database_url: str | None = None) -> FastAPI:
    engine = create_engine(
        database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        connect_args={"check_same_thread": False},
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        FilePath(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
        try:
            SQLModel.metadata.create_all(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="API Guardian", version="0.1.0", lifespan=lifespan)

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
