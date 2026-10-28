FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so this layer is cached across code-only changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY fintrack ./fintrack
COPY scripts ./scripts

# Run as an unprivileged user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "fintrack.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
