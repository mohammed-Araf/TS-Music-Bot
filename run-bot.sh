#!/bin/bash
set -e

echo "=== Setting up environment ==="
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

echo "=== Starting PulseAudio ==="
pulseaudio --check || pulseaudio --start --exit-idle-time=-1
sleep 2

# Start a dedicated Xvfb display for TeamSpeak (used inside startTeamSpeak)
echo "=== Starting Xvfb on :99 ==="
pkill Xvfb || true
sleep 1
Xvfb :99 -screen 0 1024x768x24 &
sleep 2
export DISPLAY=:99

echo "=== Running TS3 MusicBot ==="
java --module-path /usr/share/openjfx/lib \
     --add-modules javafx.controls,javafx.fxml \
     -jar ts3-musicbot.jar \
     --config ts3-musicbot.config \
     --command-config commands.config

