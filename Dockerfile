# syntax=docker/dockerfile:1
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Keep Python output unbuffered so logs stream immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy and install the package defined in pyproject.toml.
COPY . /app
RUN pip install --no-cache-dir '.[db]'

# Run from the package source directory so bundled data/input and data/output paths resolve.
WORKDIR /app/src/provider_simenv

# Pass simulation arguments directly to main.py.
# Example:
#   docker run --rm simenv --pdl scenarios/s1-soja.pdl.yaml \
#     --postgres-url postgresql+psycopg2://postgres:postgres@host:5432/provider_simenv
ENTRYPOINT ["python", "main.py"]
CMD ["--pdl", "scenarios/s1-soja.pdl.yaml"]
