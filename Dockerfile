FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
ENV POETRY_VERSION=1.7.1
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VENV=/opt/poetry-venv
ENV POETRY_CACHE_DIR=/opt/.cache

# Install poetry separated from system python
RUN python3 -m venv $POETRY_VENV \
    && $POETRY_VENV/bin/pip install -U pip setuptools \
    && $POETRY_VENV/bin/pip install poetry==${POETRY_VERSION}

# Add `poetry` to PATH
ENV PATH="${PATH}:${POETRY_VENV}/bin"

# Set working directory
WORKDIR /app

# Create data directory and set permissions
RUN mkdir -p /app/data && chmod 777 /app/data

# Copy only requirements to cache them in docker layer
COPY pyproject.toml ./

# Project initialization
RUN poetry config virtualenvs.create false

# Copy the entire project, including config files and ABIs
COPY . .

# Install dependencies and the project itself with scripts
RUN poetry install --no-interaction --no-ansi && \
    poetry run pip install -e .

# Set environment variables
ENV PYTHONPATH=/app

# Verify ABI files are present
RUN ls -la /app/loop_dune/config/abis/eth/ && \
    ls -la /app/loop_dune/config/abis/bnb/ && \
    ls -la /app/loop_dune/config/abis/usd/

# Run the script
CMD ["poetry", "run", "python", "loop_dune/scripts/collect_and_upload.py", "--cron", "0 0 * * *"]