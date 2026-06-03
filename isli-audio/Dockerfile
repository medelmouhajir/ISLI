FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Pre-download default models for fast startup
RUN python -c "from faster_whisper import download_model; download_model('tiny', output_dir='/app/models/whisper')" || true
RUN mkdir -p /app/models/piper/en

EXPOSE 8400

CMD ["uvicorn", "isli_audio.main:app", "--host", "0.0.0.0", "--port", "8400", "--proxy-headers"]

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8400/health || exit 1
