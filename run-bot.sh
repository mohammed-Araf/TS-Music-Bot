#!/bin/bash
set -e

JAR_NAME="ts3-musicbot.jar"
BUILD_OUTPUT="app/build/libs/${JAR_NAME}"

# ─── Auto-build if JAR is missing ───────────────────────────────────────────
if [ ! -f "${JAR_NAME}" ]; then
    echo "=== JAR not found. Building from source... ==="

    if [ ! -f "./gradlew" ]; then
        echo "ERROR: gradlew not found. Please run this script from the project root."
        exit 1
    fi

    chmod +x ./gradlew
    ./gradlew shadowJar

    if [ ! -f "${BUILD_OUTPUT}" ]; then
        echo "ERROR: Build failed — ${BUILD_OUTPUT} not found."
        exit 1
    fi

    cp "${BUILD_OUTPUT}" "${JAR_NAME}"
    echo "=== Build complete: ${JAR_NAME} ==="
fi

# ─── Check Configuration ───────────────────────────────────────────────────
if [ ! -f "ts3-musicbot.config" ]; then
    echo "=== ts3-musicbot.config not found! Creating from template... ==="
    cp ts3-musicbot.config.example ts3-musicbot.config
    echo "ERROR: Please configure your TeamSpeak and Spotify settings in 'ts3-musicbot.config' before running again."
    exit 1
fi

# ─── Environment ─────────────────────────────────────────────────────────────
echo "=== Setting up environment ==="
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

# ─── PulseAudio ──────────────────────────────────────────────────────────────
echo "=== Starting PulseAudio ==="
pulseaudio --check || pulseaudio --start --exit-idle-time=-1
sleep 2

# ─── Xvfb (virtual display for TS3 GUI) ──────────────────────────────────────
echo "=== Starting Xvfb on :99 ==="
pkill Xvfb || true
sleep 1
Xvfb :99 -screen 0 800x600x16 &
sleep 2
export DISPLAY=:99

# ─── Launch Bot ──────────────────────────────────────────────────────────────
echo "=== Running TS3 MusicBot ==="
nice -n 10 java --module-path /usr/share/openjfx/lib \
     --add-modules javafx.controls,javafx.fxml \
     -jar "${JAR_NAME}" \
     --config ts3-musicbot.config \
     --command-config commands.config
