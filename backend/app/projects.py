from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    field_validator,
)
from sqlmodel import Field, SQLModel

ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
ProjectDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=1000)
]


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    base_url: HttpUrl
    description: ProjectDescription | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, url: HttpUrl) -> HttpUrl:
        if url.username is not None or url.password is not None:
            raise ValueError("Base URL must not include credentials")
        if url.query is not None or url.fragment is not None:
            raise ValueError("Base URL must not include a query string or fragment")
        return url


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: ProjectName
    base_url: HttpUrl
    description: ProjectDescription | None


class ApiProject(SQLModel, table=True):
    __tablename__ = "api_projects"
    __table_args__ = {"sqlite_autoincrement": True}

    id: int | None = Field(default=None, primary_key=True)
    name: str
    base_url: str
    description: str | None = None
