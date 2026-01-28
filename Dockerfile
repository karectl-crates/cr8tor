# Install uv
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Change the working directory to the `app` directory
WORKDIR /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable --no-dev --compile-bytecode

# Copy the project into the intermediate image
ADD . /app

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --no-dev --compile-bytecode

FROM python:3.12-slim

# Create non-root user
RUN groupadd -r -g 1000 appuser && useradd -r -u 1000 -g appuser appuser

WORKDIR /app

# Change ownership of the app directory to appuser
RUN chown -R appuser:appuser /app

# Copy the environment from builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv .venv

# Switch to non-root user
USER 1000

# Run the application
CMD ["/app/.venv/bin/cr8tor", "operator"]
