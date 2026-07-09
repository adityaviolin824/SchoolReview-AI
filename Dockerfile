# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend-final

COPY frontend-final/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend-final/ ./
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build


FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        libgdk-pixbuf-2.0-0 \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libharfbuzz-subset0 \
        libjpeg62-turbo \
        libopenjp2-7 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libsm6 \
        libxext6 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/school_safety_validator ./school_safety_validator
COPY backend/utility_files ./utility_files
COPY --from=frontend-builder /app/frontend-final/dist ./static/frontend

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "school_safety_validator.api.fastapi_application:app", "--host", "0.0.0.0", "--port", "8000"]
