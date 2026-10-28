#!/usr/bin/env bash
# Starts the TS3 client and auto-connects via a ts3server:// URL.
set -euo pipefail

enc() { python3 -c 'import sys,urllib.parse as u; print(u.quote(sys.argv[1], safe=""))' "$1"; }

URL="ts3server://${TS_HOST}?port=${TS_PORT}&nickname=$(enc "${TS_NICK}")"
[ -n "${TS_CHANNEL:-}" ]          && URL="${URL}&channel=$(enc "${TS_CHANNEL}")"
[ -n "${TS_SERVER_PASSWORD:-}" ]  && URL="${URL}&password=$(enc "${TS_SERVER_PASSWORD}")"
[ -n "${TS_CHANNEL_PASSWORD:-}" ] && URL="${URL}&channelpassword=$(enc "${TS_CHANNEL_PASSWORD}")"

echo "${URL}" > /tmp/ts_url      # used by the controller's !reconnect

export QT_X11_NO_MITSHM=1
cd /opt/ts3client
exec ./ts3client_runscript.sh "${URL}"
