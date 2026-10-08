#!/usr/bin/env bash
set -euo pipefail

tag=${1:?Usage: check-live.sh exact-image-tag}
base=http://192.168.50.12:8080
actual=$(docker inspect sd2026-web-1 --format '{{.Config.Image}}')
test "$actual" = "$tag"

# The game title can evolve during final editorial work; this checks the stable
# release entry point instead of freezing a particular display title here.
curl --fail --silent --show-error "$base/" | grep -q '<main id="game"'
curl --fail --silent --show-error -o /dev/null "$base/legacy/"
curl --fail --silent --show-error -o /dev/null "$base/docs/first-shift-scenario.html"
curl --fail --silent --show-error -o /dev/null "$base/galaxy-shift.zip"
docker inspect sd2026-comments-1 --format 'comments={{.State.Running}} image={{.Config.Image}}'
printf 'local upstream verified: %s\n' "$tag"
