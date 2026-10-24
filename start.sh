#!/bin/sh
set -eu

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "Falta uv. Instálalo desde https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Falta ffmpeg. En Debian/Ubuntu: sudo apt install ffmpeg" >&2
  exit 1
fi

uv sync --locked
uv run --locked whistle-web setup
exec uv run --locked whistle-web "$@"
