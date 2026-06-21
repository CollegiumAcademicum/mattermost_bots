#!/usr/bin/env bash
set -euo pipefail

POSTBOT_IMAGE="philippbtz/mattermost-postbot"
WEBUI_IMAGE="philippbtz/mattermost-webui"

# Usage: ./publish.sh [postbot|webui] [version]
TARGET="${1:-all}"
VERSION="${2:-}"

PLATFORMS="linux/amd64,linux/arm64"

build_and_push() {
  local image="$1"
  local context="$2"
  local dockerfile="$3"

  local tags=("-t" "${image}:latest")
  if [[ -n "${VERSION}" ]]; then
    tags+=("-t" "${image}:${VERSION}")
  fi

  echo "==> Building and pushing ${image} (${PLATFORMS})"
  docker buildx build \
    --platform "${PLATFORMS}" \
    "${tags[@]}" \
    -f "${dockerfile}" \
    --push \
    "${context}"
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
