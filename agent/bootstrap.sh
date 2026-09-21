#!/bin/sh
# Offline bootstrap using the already-installed pinned interpreter and uv backend.
set -eu
AGENT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if [ "$(uv --version | cut -d ' ' -f 2)" != "0.10.9" ]; then
  echo 'Expected uv 0.10.9; install the pinned tool separately before bootstrap.' >&2
  exit 2
fi
if [ -L "$AGENT_DIR/.venv" ]; then
  echo 'Refusing a symlinked agent environment.' >&2
  exit 1
fi
if [ -e "$AGENT_DIR/.venv" ]; then
  if [ ! -x "$AGENT_DIR/.venv/bin/python" ] || \
     [ "$("$AGENT_DIR/.venv/bin/python" -c 'import platform; print(platform.python_version())')" != '3.13.12' ]; then
    echo 'Existing agent environment has a different identity; preserve it and resolve manually.' >&2
    exit 1
  fi
fi
unset UV_PROJECT_ENVIRONMENT UV_CACHE_DIR
export PYTHONDONTWRITEBYTECODE=1
cd "$AGENT_DIR/.."
exec uv sync --project "$AGENT_DIR" --locked --offline --no-python-downloads
