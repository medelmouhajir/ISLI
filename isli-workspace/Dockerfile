FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app/src
EXPOSE 8300

CMD ["uvicorn", "isli_workspace.main:app", "--host", "0.0.0.0", "--port", "8300"]
