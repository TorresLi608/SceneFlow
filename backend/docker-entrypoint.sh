#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
  # A host bind mount hides the directory ownership set in the image.
  mkdir -p /app/data/private_generated
  chown -R app:app /app/data
  chmod 700 /app/data
  exec gosu app "$@"
fi

exec "$@"
