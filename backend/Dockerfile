FROM ghcr.io/astral-sh/uv:0.9.18 AS uv
FROM python:3.14-slim

COPY --from=uv /uv /bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    DATABASE_URL=sqlite:////app/data/api_guardian.db

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev && \
    groupadd --gid 10001 appuser && \
    useradd --uid 10001 --gid 10001 --no-create-home appuser && \
    install -d -o appuser -g appuser /app/data
COPY app ./app

USER appuser
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
