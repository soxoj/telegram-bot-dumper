#!/bin/sh
# Start the web viewer with live mode and dumping of new bots, reading API_ID/API_HASH
# (and optional PORT/HOST) from .env next to this script. Extra arguments go to
# webapp/server.py, e.g. a dump folder or --allow-public.
set -e
dir=$(dirname "$0")
if [ -f "$dir/.env" ]; then
  set -a
  . "$dir/.env"
  set +a
fi
if [ -z "$API_ID" ] || [ -z "$API_HASH" ]; then
  echo "API_ID and API_HASH are not set. Run 'cp .env.example .env' and fill them in from https://my.telegram.org" >&2
  exit 1
fi
exec python3 "$dir/webapp/server.py" --allow-new-dumps "$@"
