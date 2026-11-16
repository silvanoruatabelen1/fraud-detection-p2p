# syntax=docker/dockerfile:1
# Reproductor del tráfico real del período de prueba.
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --only-group replayer --no-install-project

FROM python:3.13-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY replayer ./replayer
COPY data/demo/replay.parquet ./data/demo/replay.parquet
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 TZ=UTC
USER app
ENTRYPOINT ["python", "-m", "replayer.replay"]
