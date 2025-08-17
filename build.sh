#!/bin/bash
set -e

IMAGE_NAME="demucs-gpu"

# Detect Apple Silicon (arm64)
if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  echo "🛠 Detected Apple Silicon (arm64) — building for linux/amd64 with buildx..."
  docker buildx build --platform linux/amd64 -t "$IMAGE_NAME" --load .
else
  echo "🛠 Building natively..."
  docker build -t "$IMAGE_NAME" .
fi

