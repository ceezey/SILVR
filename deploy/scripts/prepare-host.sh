#!/usr/bin/env sh
set -eu
# Work in the repo root (run as the ubuntu user, never with sudo: the folders must stay uid 1000).
cd "$(dirname "$0")/../.."

mkdir -p data logs models reports

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
fi

chmod 700 data logs models reports

printf '%s\n' "Host directories prepared. Review .env before starting paper mode."
