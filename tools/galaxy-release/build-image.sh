#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
tag=${1:?Usage: tools/galaxy-release/build-image.sh sd2026-public:galaxy-YYYYMMDD-N}

case "$tag" in sd2026-public:galaxy-*) ;; *) echo 'Tag must start sd2026-public:galaxy-' >&2; exit 2;; esac

test -f "$root/designlab/galaxy-shift/releases/web/index.html"
test -f "$root/designlab/galaxy-shift/releases/web/build.json"
test -f "$root/designlab/galaxy-shift/releases/galaxy-shift.zip"
base_id=$(docker image inspect sd2026-public:scenario-comments --format '{{.Id}}')
test "$base_id" = sha256:8233f9ba006d051228a7f117bd13c7ebf0c108758e618d3cb99fe3d6b97d7921
revision=$(git -C "$root" rev-parse HEAD)

docker build --builder default --pull=false \
  --label "org.opencontainers.image.revision=$revision" \
  --label "org.opencontainers.image.title=Science Day: Nika and model" \
  --label "org.opencontainers.image.base.name=sd2026-public:scenario-comments" \
  -t "$tag" -f "$root/tools/galaxy-release/Dockerfile" "$root"

docker image inspect "$tag" --format 'image={{index .RepoTags 0}} id={{.Id}} created={{.Created}}'
