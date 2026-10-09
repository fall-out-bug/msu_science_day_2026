#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
tag=${1:?Usage: tools/galaxy-release/deploy.sh sd2026-public:galaxy-YYYYMMDD-N}
docker image inspect "$tag" >/dev/null

telemetry_tag=${GALAXY_TELEMETRY_IMAGE:-sd2026-telemetry:complete-20261008-1}
docker image inspect "$telemetry_tag" >/dev/null
telemetry_data_dir=${GALAXY_TELEMETRY_DATA_DIR:-"$HOME/.local/share/science-day/galaxy-telemetry"}
mkdir -p "$telemetry_data_dir"
chmod 700 "$telemetry_data_dir"
comments_before=$(docker inspect sd2026-comments-1 --format '{{.Id}} {{.State.StartedAt}}')
# Start the separate private event receiver before the nginx route uses it.
GALAXY_PUBLIC_IMAGE="$tag" GALAXY_TELEMETRY_IMAGE="$telemetry_tag" GALAXY_TELEMETRY_DATA_DIR="$telemetry_data_dir" docker compose \
  -f "$root/compose.public.yaml" \
  -f "$root/tools/galaxy-release/compose.override.yaml" \
  -f "$root/tools/galaxy-telemetry/compose.telemetry.yaml" \
  up -d --no-build --pull never --no-deps --wait --wait-timeout 45 telemetry
# This recreates only sd2026-web-1. It does not rebuild, restart, or replace
# sd2026-comments-1; its SQLite volume is untouched.
GALAXY_PUBLIC_IMAGE="$tag" docker compose \
  -f "$root/compose.public.yaml" \
  -f "$root/tools/galaxy-release/compose.override.yaml" \
  up -d --no-build --pull never --no-deps web

"$root/tools/galaxy-release/check-live.sh" "$tag"

comments_after=$(docker inspect sd2026-comments-1 --format '{{.Id}} {{.State.StartedAt}}')
test "$comments_before" = "$comments_after"
printf 'comments container identity and start time unchanged\n'
