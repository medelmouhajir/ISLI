FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY src ./src

EXPOSE 8200

CMD ["uvicorn", "isli_channels.main:app", "--host", "0.0.0.0", "--port", "8200", "--proxy-headers"]
