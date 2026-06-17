# Use Python 3.13+ as required by pyproject.toml
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Copy requirements files for installation
COPY requirements.txt .
# Optional: Copy dev requirements if needed for debugging
# COPY requirements-dev.txt .

# Install dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy your package source code
COPY src/ /app/src/
COPY pyproject.toml .

# Install your package
RUN pip install -e .

# Set environment variables if needed
# ENV PYTHONPATH=/app

# Command to run the bot via the unified CLI.
# Pass the platform as the container command, e.g. `docker run <image> discord`
# or `docker run <image> slack`. Defaults to discord.
# Note: this assumes the matching config (discord_config.yaml / slack_config.yaml) is mounted at runtime.
ENTRYPOINT ["innieme"]
CMD ["discord"]