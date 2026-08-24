#!/bin/sh
# Run the backend self-checks one file per process.
#
# `tests/run_all.py` runpy's everything in a single process and aborts on the first
# failure, so a green run there proves less than it looks (see CLAUDE.md). Each file gets
# its own interpreter and its own throwaway database here; the real dev database at
# backend/sceneflow.db is never touched.
FAILED=""
for name in "$@"; do
  DB=$(mktemp -u /tmp/sf_test_XXXXXX.db)
  if SCENEFLOW_DB_PATH="$DB" PYTHONPATH=. .venv/bin/python "tests/$name.py" >"/tmp/$name.log" 2>&1; then
    echo "PASS  $name"
  else
    echo "FAIL  $name"
    FAILED="$FAILED $name"
  fi
  rm -f "$DB"
done
if [ -n "$FAILED" ]; then
  echo ""
  echo "failed:$FAILED"
  echo "logs in /tmp/<name>.log"
  exit 1
fi
