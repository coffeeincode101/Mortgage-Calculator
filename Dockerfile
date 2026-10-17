
FROM python:3.15-slim

# Configure Python and application behaviour.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLOUD_ENV=true \
    MORTGAGE_OUTPUT=/app/output

WORKDIR /app

# Install dependencies before copying the application.
# This allows Docker to reuse the dependency layer.
COPY pyproject.toml ./

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir --group runtime

# Copy application source code.
COPY src/ ./src/

# Prepare writable directories and a non-root application user.
RUN mkdir -p /app/data /app/output && \
    useradd --create-home mortgage && \
    chown -R mortgage:mortgage /app

USER mortgage

# Run the application.
CMD ["python", "-m", "src.mortgage"]
