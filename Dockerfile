FROM python:3.12-slim

# uv pinned to the minor used to generate uv.lock (flightdeck pattern)
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

# openssh-client IS the terminal path (pod pty -> ssh -tt -> tmux on the host)
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends openssh-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_LINK_MODE=copy

# dependency layer first (only invalidated when the lockfile changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# uid 1000 == guillermo on forge: makes the 0700 ro hostPaths readable
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000
CMD ["python", "-m", "termweb.server"]
