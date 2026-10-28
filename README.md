<div align="center">

# 🎵 TeamSpeak Spotify Bot (Dockerized)

**A high-performance, containerized TeamSpeak 3 Spotify Connect music bot.**

[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python)](https://python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux%20amd64-FCC624?style=flat-square&logo=linux)](https://www.linux.org/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## 🚀 Architecture

Each bot runs inside an isolated, lightweight Docker container:

```
TeamSpeak Channel Chat (!p ...) 
               │
               ▼
   Python Async Controller (ClientQuery API on 127.0.0.1:25639)
               │
               ▼
   go-librespot (Spotify Connect Receiver + Local HTTP API on :3678)
               │ audio
               ▼
   PulseAudio Null Sink "music"
               │ monitor
               ▼
   Headless TeamSpeak 3 Client (Xvfb :99)
               │
               ▼
   TeamSpeak Server Channel (Opus Music)
```

- **Zero Host Audio Contamination:** PulseAudio and virtual null sinks run entirely inside the container.
- **No yt-dlp or D-Bus / MPRIS Brittle Dependencies:** Direct Spotify Connect streaming using `go-librespot`.
- **Ultra-lightweight:** Python asyncio controller (~30MB RAM) replaces heavy JVM runtimes.
- **Multi-bot Ready:** Run N bots on one VPS simply by adding `bot1`, `bot2`, etc. in `docker-compose.yml`.

---

## 📋 Prerequisites

1. **Linux x86_64 host / VPS** with Docker & Docker Compose v2.
2. **Spotify Premium Account** (one individual account per bot).
3. **Spotify Developer App** (free from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)) for search.
4. **TeamSpeak 3 Server** with permissions to join and speak (Opus Music codec recommended).

---

## 🛠️ Quick Start

### 1. Configure Shared Settings

Check `.env.common` and ensure your TeamSpeak server and Spotify Developer App credentials are set:

```env
TS_HOST=your.teamspeak.server
TS_PORT=9987
TS_CHANNEL=Music
TS_CHANNEL_PASSWORD=

CMD_PREFIX=!
CMD_COOLDOWN=1.5
MAX_VOLUME=80
INITIAL_VOLUME=40

SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

### 2. Configure Bot 1

Open `bots/bot1.env`:

```env
TS_NICK=MusicBot1
SPOTIFY_DEVICE_NAME=MusicBot1
TS_CLIENTQUERY_APIKEY=          # filled after Step 4
ADMIN_UIDS=your_teamspeak_uid=  # comma-separated TS unique IDs
```

### 3. Build the Image

```bash
docker compose build
```

### 4. First-Time Setup (Spotify Login & TS3 API Key)

Run the bot in interactive setup mode:

```bash
mkdir -p data/bot1
docker compose run --rm --service-ports --name tsbot1-setup \
  -e SETUP_MODE=1 -e VNC_PASSWORD=myvncpass \
  -p 127.0.0.1:8888:8889 -p 127.0.0.1:5900:5900 \
  bot1
```

*(If on a remote VPS, create an SSH tunnel: `ssh -L 8888:127.0.0.1:8888 -L 5900:127.0.0.1:5900 user@your-vps`)*

1. **Link Spotify:** In the terminal logs, `go-librespot` will print a Spotify authorization URL. Open it in your browser, log in with this bot's Spotify Premium account, and approve. The browser redirects to `http://127.0.0.1:8888/...`, saving permanent credentials into `data/bot1/librespot/`.
2. **Configure TeamSpeak 3 via VNC:** Connect a VNC viewer (e.g., TigerVNC, RealVNC, Screen Sharing) to `127.0.0.1:5900` with the password `myvncpass`.
   - Go to **Tools → Options → Plugins** (or **Settings → Plugins**).
   - Ensure **ClientQuery** is enabled, click its settings, and **copy the API Key**.
   - Paste the API key into `bots/bot1.env` under `TS_CLIENTQUERY_APIKEY`.
   - Ensure **Capture** is set to `Default` (Continuous Transmission) and **Playback** is set to `Default`.
   - Note the bot's Identity Unique ID to grant server permissions.
3. Stop the setup container (`Ctrl+C`).

### 5. Start the Bot

Start the bot in the background:

```bash
docker compose up -d bot1
docker compose logs -f bot1
```

---

## 🎧 Chat Commands

All commands use the prefix defined in `.env.common` (default `!`):

| Command | Permission | Description |
|---|---|---|
| `!play <query \| link>` | Everyone | Search & play, or stream direct Spotify track/album/playlist URL. Resumes if empty. |
| `!queue <query \| link>` | Everyone | Add track or Spotify URL to playback queue. |
| `!pause` | Everyone | Pause playback. |
| `!resume` (or `!r`) | Everyone | Resume playback. |
| `!skip` (or `!next`, `!s`) | Everyone | Skip to next track. |
| `!prev` (or `!back`) | Everyone | Return to previous track. |
| `!vol <0-80>` (or `!v`) | Everyone | Adjust volume (clamped to `MAX_VOLUME`). |
| `!np` | Everyone | Show currently playing song title and artist. |
| `!help` | Everyone | Show list of available commands. |
| `!restart` | Admin | Restart the container process. |
| `!reconnect` | Admin | Reconnect TeamSpeak 3 client to the channel. |
| `!audio` | Admin | Restart `go-librespot` audio engine. |
| `!status` | Admin | Check Spotify API connection and health. |

---

## 👥 Scaling: Adding More Bots

Running multiple bots is as simple as:

1. Copy `bots/bot1.example.env` to `bots/bot2.env` with a unique `TS_NICK` and `SPOTIFY_DEVICE_NAME`.
2. Uncomment or add the `bot2` service in `docker-compose.yml`.
3. Run Step 4 (setup mode) for `bot2` with its own Spotify Premium account.
4. Launch with `docker compose up -d bot2`.

---

## 📜 Preserved Legacy Code

The previous Kotlin/JavaFX bot implementation is preserved intact on the [`legacy-kotlin-bot`](file:///Users/araf/Documents/Projects/ts3-musicbot-master) git branch. To inspect it:

```bash
git checkout legacy-kotlin-bot
```

To switch back to the modern Docker bot:

```bash
git checkout main
```
