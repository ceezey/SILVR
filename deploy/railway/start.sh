#!/bin/sh
# Railway entrypoint. Runs from the volume at /app/var so logs/, reports/, models/
# and the kill-switch file survive redeploys.
set -eu
mkdir -p /app/var
cd /app/var
# shortcut: the dashboard is not restarted if it dies; it comes back on the next deploy or restart.
python -m silver_bot.monitoring.dashboard_server --host 0.0.0.0 --port "${PORT:-8765}" \
    --allowed-host "${RAILWAY_PUBLIC_DOMAIN:-localhost}" &
exec python -m silver_bot
