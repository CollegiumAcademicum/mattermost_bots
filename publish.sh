#!/usr/bin/env bash
set -euo pipefail

POSTBOT_IMAGE="philippbtz/mattermost-postbot"
WEBUI_IMAGE="philippbtz/mattermost-webui"

# Usage: ./publish.sh [postbot|webui] [version]
TARGET="${1:-all}"
VERSION="${2:-}"

build_and_push() {
  local image="$1"
  local context="$2"
  local dockerfile="$3"

  echo "==> Building ${image}:latest"
  docker build -t "${image}:latest" -f "${dockerfile}" "${context}"

  if [[ -n "${VERSION}" ]]; then
    docker tag "${image}:latest" "${image}:${VERSION}"
  fi

  echo "==> Pushing ${image}:latest"
  docker push "${image}:latest"

  if [[ -n "${VERSION}" ]]; then
    echo "==> Pushing ${image}:${VERSION}"
    docker push "${image}:${VERSION}"
  fi
}

case "${TARGET}" in
  postbot)
    build_and_push "${POSTBOT_IMAGE}" "." "postbot/Dockerfile"
    ;;
  webui)
    build_and_push "${WEBUI_IMAGE}" "webui" "webui/Dockerfile"
    ;;
  all)
    build_and_push "${POSTBOT_IMAGE}" "." "postbot/Dockerfile"
    build_and_push "${WEBUI_IMAGE}" "webui" "webui/Dockerfile"
    ;;
  *)
    echo "Usage: $0 [postbot|webui|all] [version]"
    exit 1
    ;;
esac

echo "Done."
