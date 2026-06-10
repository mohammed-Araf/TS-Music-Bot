<div align="center">

# 🎵 TS3 Music Bot

**A lightweight, streaming-only TeamSpeak 3 music bot — built for Linux VPS environments.**

[![Language](https://img.shields.io/badge/language-Kotlin-7F52FF?style=flat-square&logo=kotlin)](https://kotlinlang.org/)
[![Platform](https://img.shields.io/badge/platform-Linux-FCC624?style=flat-square&logo=linux)](https://www.linux.org/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## Overview

TS3 Music Bot connects to a TeamSpeak 3 server and plays music directly into a channel via a PulseAudio virtual loopback device. It streams from **Spotify Premium** (via `ncspot`) and supports **YouTube**, **SoundCloud**, and **Bandcamp** (via `mpv`). The bot runs the official TS3 desktop client headlessly inside an `Xvfb` virtual display.

> **No downloads. No buffering.** Music is streamed in real-time, keeping CPU usage under 15% and RAM well within 1 GB VPS constraints.

---

## 🚀 Quick Start (Setup in 3 Steps)

Setting up the music bot is now fully automated! Follow these 3 simple steps:

### 1. Clone the Repository
Connect to your Linux server via SSH and run:
```bash
git clone https://github.com/mohammed-Araf/TS-Music-Bot.git
cd TS-Music-Bot
```

### 2. Install Dependencies
Install all required packages (Java, PulseAudio, TeamSpeak, ncspot, and spotify_player) automatically:
```bash
chmod +x setup-server.sh
./setup-server.sh
```

### 3. Configure and Run
Run the bot launcher:
```bash
chmod +x run-bot.sh
./run-bot.sh
```
* **First run:** The script will automatically create `ts3-musicbot.config`.
* **Configure:** Open `ts3-musicbot.config` using a text editor (e.g., `nano ts3-musicbot.config`) and enter your TeamSpeak server address, nickname, and Spotify credentials.
* **Launch:** Run `./run-bot.sh` again to compile the JAR and start the bot!

*Note: The first time you use Spotify playback, follow the authorization link printed in the console to authorize Spotify in your browser, and paste the redirect link back into the terminal. The login token will be saved permanently.*

---

## Architecture

```
TeamSpeak Channel Chat
        │
        │ !p <query>
        ▼
TS3 MusicBot (Kotlin / JVM)
        │
        ├──► Spotify Web API → fetch track metadata / link
        │
        ├──► ncspot (via MPRIS / D-Bus in tmux)
        │         │
        │         └──► PulseAudio Loopback Device
        │                       │
        └──────────────────────► TS3 Desktop Client (Xvfb :99)
                                          │
                                          └──► TeamSpeak 3 Server Channel
```

---

## Features

| Feature | Description |
|---|---|
| **Smart Play / Queue** | `!p` plays immediately if idle; `!play` queues if something is already playing |
| **Spotify Defaults** | Plain-text queries (e.g. `!p Alan Walker Faded`) resolve to Spotify automatically |
| **Multi-Service** | Spotify (native), YouTube, SoundCloud, Bandcamp |
| **Permission Control** | Restrict commands by TeamSpeak Server Group ID |
| **Custom Commands** | Remap any command prefix via `commands.config` |
| **Pre-Shuffle** | Shuffle albums/playlists before adding to queue |
| **Restart Command** | `!restart` to recover from audio freezes without SSH |

---

## Requirements

Ensure the following are installed on your **Linux server**:

- **Java 17+** (JDK)
- **OpenJFX** — JavaFX libraries (e.g. `/usr/share/openjfx/lib`)
- **PulseAudio** — virtual audio loopback
- **Xvfb** — headless virtual display
- **tmux** — terminal multiplexer for background sessions
- **ncspot** — ncurses Spotify client *(requires Spotify Premium)*
- **mpv** — media player for non-Spotify sources
- **TeamSpeak 3 Client** — official Linux amd64 desktop client

---

## Configuration

### `ts3-musicbot.config` — Bot Settings

```ini
# Server connection
serverAddress=your.server.ip
serverPort=9987
channelPath=Music
channelPassword=

# Bot identity
botNickname=MusicBot

# Spotify player backend
spotifyPlayer=ncspot
spotifyUsername=your_spotify_email
spotifyPassword=your_spotify_password
```

---

### `commands.config` — Command Mapping

Remap any command to a custom name. The prefix character is set with `COMMAND_PREFIX`.

```ini
COMMAND_PREFIX=!

QUEUE_PLAYNOW=p
QUEUE_ADD=play
QUEUE_SKIP=s
QUEUE_STOP=stop
QUEUE_PAUSE=pause
QUEUE_RESUME=r
QUEUE_LIST=q
QUEUE_CLEAR=c
QUEUE_DELETE=rm
QUEUE_MOVE=mv
VOLUME=v
QUEUE_REPEAT=loop
QUEUE_NOWPLAYING=np
INFO=src
RESTART=restart
```

---

### `permissions.yml` — Access Control

Control who can use music commands using **TeamSpeak Server Group IDs**.

```yaml
permissions:
  # Enable or disable the permissions module entirely
  enabled: true

  # Global TS badge GUIDs required to use restricted commands
  # Set to [] to disable badge-based checks (use server groups instead)
  required_badges: []

  # Server Group IDs allowed to use restricted commands
  # Find your Group ID in: TS3 Server → Permissions → Server Groups
  required_server_groups:
    - 50   # e.g. "DJ Private"

  # Cache settings — reduce TTL for faster group change propagation
  cache_badges: true
  cache_ttl_seconds: 5

  # Message shown when a user is denied
  deny_message: "You are not allowed to use music commands."

  # Commands usable by everyone, regardless of permissions
  public_commands:
    - "np"
    - "q"
    - "src"
```

> **Tip:** To find your server group ID, look at `TS3 → Permissions → Server Groups`. The ID is the number next to the group name. You can also see a user's groups in the bot console output when they run a command:
> ```
> [PERMISSIONS] Client DJ_User (ID: 15): Badges=[], Groups=[50, 8]
> ```

---

## Commands

All commands use the prefix defined in `commands.config` (default: `!`).

| Command | Arguments | Description |
|:---|:---|:---|
| `!p` | `<query / link>` | **Smart Play** — plays immediately if idle, or queues if already playing |
| `!play` | `<query / link>` | **Force Queue** — always adds to queue |
| `!s` | — | Skip current track |
| `!stop` | — | Stop playback and clear queue |
| `!pause` | — | Pause playback |
| `!r` | — | Resume playback |
| `!q` | — | Show next 15 tracks in queue |
| `!c` | — | Clear the entire queue |
| `!rm` | `<index>` | Remove track at position (0-indexed) |
| `!mv` | `<from> -p <to>` | Move track from one position to another |
| `!v` | `<0–100>` | Set playback volume |
| `!loop` | `<count>` | Repeat current track `<count>` times |
| `!np` | — | Show currently playing song info |
| `!src` | `<query / link>` | Show source/metadata for a query |
| `!restart` | — | Restart the media player (fixes audio freezes) |

### Query Prefixes

| Prefix | Service |
|:---|:---|
| *(none)* | Spotify (default) |
| `sp track` | Spotify track |
| `sp album` | Spotify album |
| `sp playlist` | Spotify playlist |
| `yt` | YouTube |
| `sc` | SoundCloud |
| `bc` | Bandcamp |

---

## Building from Source

> **The JAR is not included in the repository.** You must build it yourself before running the bot.

### Prerequisites

- **Java 11+ JDK** installed (JDK 17 recommended)
- **Git** to clone the repo

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/mohammed-Araf/TS-Music-Bot.git
cd TS-Music-Bot

# 2. Build the fat JAR (includes all dependencies)
./gradlew shadowJar
```

The compiled JAR will be output to:
```
app/build/libs/ts3-musicbot.jar
```

Copy it to wherever you run the bot from:
```bash
cp app/build/libs/ts3-musicbot.jar ~/ts3-musicbot.jar
```

> **Windows users:** Use `gradlew.bat shadowJar` instead of `./gradlew shadowJar`.

---

## Running the Bot

### Startup Script (`run-bot.sh`)

Create this script on your server and make it executable (`chmod +x run-bot.sh`):

```bash
#!/bin/bash
set -e

# D-Bus session (required for ncspot MPRIS controls)
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

# Start PulseAudio if not running
pulseaudio --check || pulseaudio --start --exit-idle-time=-1
sleep 2

# Start virtual display
Xvfb :99 -screen 0 1024x768x24 &
sleep 2
export DISPLAY=:99

# Launch the bot
java --module-path /usr/share/openjfx/lib \
     --add-modules javafx.controls,javafx.fxml \
     -jar ts3-musicbot.jar \
     --config ts3-musicbot.config \
     --command-config commands.config
```

### Running as a systemd Service (Recommended)

1. Create `/etc/systemd/system/ts3-musicbot.service`:

```ini
[Unit]
Description=TS3 Music Bot
After=network.target

[Service]
WorkingDirectory=/home/ubuntu
ExecStart=/home/ubuntu/run-bot.sh
Restart=on-failure
RestartSec=10
User=ubuntu
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

2. Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ts3-musicbot
sudo systemctl start ts3-musicbot
```

3. View live logs:

```bash
sudo journalctl -u ts3-musicbot -f -n 100
```

---

## Troubleshooting

| Problem | Solution |
|:---|:---|
| Audio is frozen / silent | Use `!restart` in chat to reset the media player |
| Commands not working for a user | Check their Server Group ID matches `required_server_groups` in `permissions.yml` |
| `ncspot` not found | Ensure `ncspot` is installed and on `$PATH` for the bot's user |
| TS3 client won't start | Confirm `Xvfb` is running and `DISPLAY=:99` is exported before launching |
| Volume too low/loud | Use `!v <0-100>` to adjust, or set PulseAudio sink volume via `pactl` |

---

## License

This project is licensed under the [MIT License](LICENSE).
