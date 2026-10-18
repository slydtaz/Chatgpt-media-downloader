#!/bin/sh
set -eu
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  exec python3 -m app.bootstrap "$@"
elif command -v python >/dev/null 2>&1; then
  exec python -m app.bootstrap "$@"
else
  echo "Python 3.x não foi encontrado." >&2
  exit 1
fi
