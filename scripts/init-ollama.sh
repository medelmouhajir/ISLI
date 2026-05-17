#!/bin/bash
set -e

OLLAMA_HOST=${OLLAMA_HOST:-"http://localhost:11434"}
MODELS=("qwen2.5:7b" "nomic-embed-text")

echo "Waiting for Ollama to be ready at $OLLAMA_HOST..."
until curl -s -f "$OLLAMA_HOST/api/tags" > /dev/null; do
  sleep 2
done

for model in "${MODELS[@]}"; do
  echo "Pulling model: $model"
  curl -s -X POST "$OLLAMA_HOST/api/pull" -d "{\"name\": \"$model\"}"
done

echo "Ollama initialization complete."
