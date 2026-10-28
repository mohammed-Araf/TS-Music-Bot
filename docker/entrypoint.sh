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
  : "${TS_CLIENTQUERY_APIKEY:?TS_CLIENTQUERY_APIKEY is required (see setup)}"
  : "${SPOTIFY_CLIENT_ID:?SPOTIFY_CLIENT_ID is required}"
  : "${SPOTIFY_CLIENT_SECRET:?SPOTIFY_CLIENT_SECRET is required}"
  export CONTROLLER_AUTOSTART=true
  export SETUP_AUTOSTART=false
fi

# Persistent dirs
mkdir -p /data/home /data/librespot /tmp/pulse
chown -R bot:bot /data

# Pre-seed TS3 settings database if missing
if [ ! -f /data/home/.ts3client/settings.db ] && [ -f /opt/bot/docker/templates/settings.db ]; then
  mkdir -p /data/home/.ts3client
  cp /opt/bot/docker/templates/settings.db /data/home/.ts3client/settings.db
  chown -R bot:bot /data/home/.ts3client
fi

# Render go-librespot config (state/credentials persist alongside it in /data/librespot)
envsubst < /opt/bot/docker/go-librespot.config.tmpl.yml > /data/librespot/config.yml
chown bot:bot /data/librespot/config.yml

exec /usr/bin/supervisord -n -c /opt/bot/docker/supervisord.conf
