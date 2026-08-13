#!/bin/sh
set -eu

cd "$(dirname "$0")"

mkdir -p backups
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/sceneflow-backup.XXXXXX")
archive="backups/sceneflow-$(date +%Y%m%d-%H%M%S).tar.gz"
was_running=$(docker compose ps --status running --services | grep -x backend || true)

cleanup() {
  rm -rf "$work_dir"
  if [ -n "$was_running" ]; then
    docker compose start backend >/dev/null
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -n "$was_running" ]; then
  docker compose stop backend >/dev/null
fi

docker compose cp backend:/app/backend/data/sceneflow.db "$work_dir/sceneflow.db"
docker compose cp backend:/app/backend/private_generated "$work_dir/private_generated"
tar -czf "$archive" -C "$work_dir" sceneflow.db private_generated

echo "Backup created: $archive"
