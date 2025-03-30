FROM python:3.9-slim

# Install Poetry
RUN pip install poetry

# Set working directory
WORKDIR /app

# Copy poetry files
COPY pyproject.toml poetry.lock ./

# Configure poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-dev

# Copy application code
COPY loop_dune/ ./loop_dune/
COPY config/ ./config/

# Set environment variables
ENV PYTHONPATH=/app

# Run the sync service
CMD ["poetry", "run", "loop-sync"]