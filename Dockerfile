FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    unixodbc-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY requirements.txt pyproject.toml ./
RUN pip install -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser && \
    mkdir -p /home/appuser && chown -R appuser:appgroup /app /home/appuser

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import sys; from src.config import load_postgres_settings; sys.exit(0)"

CMD ["tail","-f","/dev/null"]