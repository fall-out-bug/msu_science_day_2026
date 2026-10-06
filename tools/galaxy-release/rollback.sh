#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
tag=${1:-sd2026-public:scenario-comments}
docker image inspect "$tag" >/dev/null
GALAXY_PUBLIC_IMAGE="$tag" docker compose \
  -f "$root/compose.public.yaml" \
  -f "$root/tools/galaxy-release/compose.override.yaml" \
  up -d --no-build --pull never --no-deps web
docker inspect sd2026-web-1 --format 'image={{.Config.Image}} id={{.Image}} started={{.State.StartedAt}}'
