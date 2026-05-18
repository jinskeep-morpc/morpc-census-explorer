FROM python:3.12-slim

WORKDIR /app

# System deps for geopandas / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install local wheels before PyPI resolution so patched versions are used
COPY vendor/ /vendor/
RUN pip install --no-cache-dir /vendor/morpc-*.whl /vendor/morpc_census-*.whl

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

EXPOSE 8050

CMD ["python", "-m", "app.main"]
