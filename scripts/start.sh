#!/usr/bin/env bash
# start.sh — Convenience wrapper for docker compose on WSL2.
#
# Converts Windows-style paths (H:/downloads, D:\Filmoteka) from .env
# into WSL2-compatible paths (/mnt/h/downloads, /mnt/d/Filmoteka)
# before passing control to `docker compose up`.
#
# Usage:
#   bash scripts/start.sh          # start all services (foreground)
#   bash scripts/start.sh -d       # start all services (detached)
#   bash scripts/start.sh api      # start specific service
#   bash scripts/start.sh -d api   # detached specific service
#
# All arguments are forwarded verbatim to `docker compose up`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ── Help ─────────────────────────────────────────────────────────
if [[ "${1:-}" == "--help" ]]; then
  sed -n '3,14p' "$0"
  exit 0
fi

# ── Load .env (shell-local, not exported) ────────────────────────
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi

# ── Windows → WSL2 path converter ────────────────────────────────
_convert_wsl() {
  local val="$1"
  # Match X:[/\]rest → lowercase drive + forward slashes
  if [[ "$val" =~ ^([A-Za-z]):[/\\](.*) ]]; then
    local drive="${BASH_REMATCH[1],,}"
    local rest="${BASH_REMATCH[2]//\\//}"
    echo "/mnt/$drive/$rest"
    return 0
  fi
  echo "$val"
  return 1
}

_convert_var() {
  local var="$1"
  local val="${!var:-}"
  [[ -z "$val" ]] && return
  local converted
  converted="$(_convert_wsl "$val")"
  if [[ "$converted" != "$val" ]]; then
    echo "  $var: '$val' → '$converted'"
    export "$var"="$converted"
  fi
}

echo "[start.sh] Converting Windows paths for WSL2…"
_convert_var LIBRARY_ROOT
_convert_var DOWNLOADS_ROOT

echo "[start.sh] Running: docker compose up $*"
exec docker compose up "$@"
