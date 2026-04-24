#!/bin/bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Stopping VisionGuard AI via Docker Compose..."
cd "$PROJECT_DIR"
docker compose down

echo "Services stopped."
