#!/usr/bin/env bash
set -euo pipefail

IMAGE="philippbtz/mattermost_bots"

# Optional version tag as first argument, e.g. ./publish.sh 1.2.0
VERSION="${1:-}"

docker build -t "${IMAGE}:latest" .

if [[ -n "${VERSION}" ]]; then
  docker tag "${IMAGE}:latest" "${IMAGE}:${VERSION}"
fi

docker push "${IMAGE}:latest"

if [[ -n "${VERSION}" ]]; then
  docker push "${IMAGE}:${VERSION}"
  echo "Pushed ${IMAGE}:latest and ${IMAGE}:${VERSION}"
else
  echo "Pushed ${IMAGE}:latest"
fi
