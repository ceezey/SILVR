#!/usr/bin/env sh
set -eu

mkdir -p data logs models reports

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
fi

chmod 700 data logs models reports

printf '%s\n' "Host directories prepared. Review .env before starting paper mode."
