#!/bin/bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting VisionGuard AI via Docker Compose..."
cd "$PROJECT_DIR"
docker compose up -d

echo "Services started. Use 'docker compose ps' and 'docker compose logs -f' for status."
