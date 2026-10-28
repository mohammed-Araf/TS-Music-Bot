#!/usr/bin/env bash
set -euo pipefail

SETUP_MODE="${SETUP_MODE:-0}"

# Required in all modes
: "${TS_HOST:?TS_HOST is required}"
: "${TS_NICK:?TS_NICK is required}"
: "${SPOTIFY_DEVICE_NAME:?SPOTIFY_DEVICE_NAME is required}"

export TS_PORT="${TS_PORT:-9987}"
export TS_CHANNEL="${TS_CHANNEL:-}"
export INITIAL_VOLUME="${INITIAL_VOLUME:-40}"
export VNC_PASSWORD="${VNC_PASSWORD:-changeme}"

if [ "$SETUP_MODE" = "1" ]; then
  # One-time interactive setup: VNC for the TS GUI, socat to expose the Spotify OAuth callback.
  export CONTROLLER_AUTOSTART=false
  export SETUP_AUTOSTART=true
else
  export TS_CLIENTQUERY_APIKEY="${TS_CLIENTQUERY_APIKEY:-musicbot_default_clientquery_key}"
  export SPOTIFY_CLIENT_ID="${SPOTIFY_CLIENT_ID:-}"
  export SPOTIFY_CLIENT_SECRET="${SPOTIFY_CLIENT_SECRET:-}"
  export CONTROLLER_AUTOSTART=true
  export SETUP_AUTOSTART=false
fi

# Persistent dirs
mkdir -p /data/home /data/librespot /tmp/pulse
chown -R bot:bot /data /tmp/pulse
chmod 777 /tmp/pulse

# Pre-seed TS3 settings, plugins, and addons if missing
if [ -d /opt/bot/docker/templates ]; then
  mkdir -p /data/home/.ts3client/plugins
  if [ ! -f /data/home/.ts3client/settings.db ] && [ -f /opt/bot/docker/templates/settings.db ]; then
    cp /opt/bot/docker/templates/settings.db /data/home/.ts3client/settings.db
  fi
  if [ ! -f /data/home/.ts3client/addons.ini ] && [ -f /opt/bot/docker/templates/addons.ini ]; then
    cp /opt/bot/docker/templates/addons.ini /data/home/.ts3client/addons.ini
  fi
  if [ -d /opt/bot/docker/templates/plugins ]; then
    cp -rf /opt/bot/docker/templates/plugins/* /data/home/.ts3client/plugins/
  fi
  if [ -n "${TS_CLIENTQUERY_APIKEY:-}" ]; then
    cat > /data/home/.ts3client/clientquery.ini <<EOF
[General]
api_key=${TS_CLIENTQUERY_APIKEY}
logging_enabled=false
open_remote=false
EOF
  fi
  chown -R bot:bot /data/home/.ts3client
fi

# Render go-librespot config (state/credentials persist alongside it in /data/librespot)
envsubst < /opt/bot/docker/go-librespot.config.tmpl.yml > /data/librespot/config.yml
chown bot:bot /data/librespot/config.yml

exec /usr/bin/supervisord -n -c /opt/bot/docker/supervisord.conf
