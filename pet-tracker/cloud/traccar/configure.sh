#!/usr/bin/env bash
# Writes traccar.local.xml from traccar.xml and .env.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
: "${SUPABASE_URL:?set SUPABASE_URL in .env}"
: "${TRACCAR_FORWARD_SECRET:?set TRACCAR_FORWARD_SECRET in .env}"
[ "${#TRACCAR_FORWARD_SECRET}" -ge 32 ] || { echo "TRACCAR_FORWARD_SECRET needs 32+ characters" >&2; exit 1; }
sed -e "s#__SUPABASE_URL__#${SUPABASE_URL%/}#" \
    -e "s#__TRACCAR_FORWARD_SECRET__#${TRACCAR_FORWARD_SECRET}#" traccar.xml > traccar.local.xml
chmod 600 traccar.local.xml
mkdir -p data logs caddy-data
echo "traccar.local.xml written"
