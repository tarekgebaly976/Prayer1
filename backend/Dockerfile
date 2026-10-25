# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home /app app
COPY requirements.lock ./
RUN grep -vE '^(pytest|pytest-cov|ruff|mypy|pip-audit|httpx|coverage|iniconfig|pluggy|mypy_extensions|pathspec|pip-requirements-parser|pip_audit|cyclonedx|license-expression|boolean.py|packageurl|py-serializable|sortedcontainers|defusedxml|CacheControl|msgpack|toml|platformdirs|filelock|requests|urllib3|charset-normalizer|certifi|idna|rich|markdown-it-py|mdurl|Pygments|packaging|tomli|tomli_w|pip-api|pip)==' requirements.lock > req.txt \
    && pip install -r req.txt && rm req.txt
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN mkdir -p /app/var/storage && chown -R app:app /app/var
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live',timeout=4).status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "2"]
