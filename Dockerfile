# Use Python 3.9 or newer as specified in your pyproject.toml
FROM python:3.10-slim

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

# Command to run the bot
# Note: This assumes config.yaml will be mounted at runtime
ENTRYPOINT ["innieme_bot"]