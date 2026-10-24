# Use Python 3.13+ as required by pyproject.toml
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first so this layer is cached until the lockfile changes
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Copy the package source and install it
COPY src/ /app/src/
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Command to run the bot via the unified CLI.
# Pass the platform as the container command, e.g. `docker run <image> discord`
# or `docker run <image> slack`. Defaults to discord.
# Note: this assumes the matching config (discord_config.yaml / slack_config.yaml) is mounted at runtime.
ENTRYPOINT ["innieme"]
CMD ["discord"]
