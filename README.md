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

## 🛠️ Quick Start (3 Easy Steps)

### 1. Configure Settings

Copy the template configuration files:
```bash
cp .env.common.example .env.common
cp bots/bot1.example.env bots/bot1.env
```

Open `.env.common` and enter your TeamSpeak Server details:
```env
TS_HOST=your.teamspeak.server
TS_PORT=9987
TS_CHANNEL=Music
```

*(Optional: Set your bot nickname in `bots/bot1.env` if you'd like a custom name)*.

### 2. Start the Bot

Start the bot with Docker Compose:
```bash
docker compose up -d bot1
```

### 3. Connect Spotify from TeamSpeak Chat

1. Join the TeamSpeak channel where the bot has connected.
2. Type in the channel chat:
   ```text
   !login
   ```
3. The bot gives you a Spotify pairing link (`https://spotify.com/pair?code=XXXXXX`). Open it on your phone or browser, log in to Spotify Premium, and click **Confirm**.
4. The bot will automatically announce:
   ```text
   ✅ Spotify Connected! Logged in as <username>. Ready to play music!
   ```

**That's it!** You can now play music immediately:
```text
!play Bohemian Rhapsody
```

---

## 🎧 Chat Commands

All commands use the prefix defined in `.env.common` (default `!`):

| Command | Permission | Description |
|---|---|---|
| `!play <query \| link>` | Everyone / Allowed Role | Search & play, or stream direct Spotify track/album/playlist URL. Resumes if empty. |
| `!queue <query \| link>` | Everyone / Allowed Role | Add track or Spotify URL to playback queue. |
| `!pause` | Everyone / Allowed Role | Pause playback. |
| `!resume` (or `!r`) | Everyone / Allowed Role | Resume playback. |
| `!skip` (or `!next`, `!s`) | Everyone / Allowed Role | Skip to next track. |
| `!prev` (or `!back`) | Everyone / Allowed Role | Return to previous track. |
| `!vol <0-80>` (or `!v`) | Everyone / Allowed Role | Adjust volume (clamped to `MAX_VOLUME`). |
| `!np` | Everyone / Allowed Role | Show currently playing song title and artist. |
| `!login` (or `!pair`) | Allowed Role / Admin | Pair a Spotify Premium account directly via `spotify.com/pair` link. |
| `!spotifykeys` | Allowed Role / Admin | Step-by-step wizard to set or update your own free Spotify Search keys. |
| `!myroles` | Everyone | View your current UID, Server Group IDs, and Channel Group ID. |
| `!help` | Everyone | Show list of available commands. |
| `!logout` | Admin | Unlink currently paired Spotify account. |
| `!restart` | Admin | Restart the container process. |
| `!reconnect` | Admin | Reconnect TeamSpeak 3 client to the channel. |
| `!audio` | Admin | Restart `go-librespot` audio engine. |
| `!status` | Admin | Check Spotify connection status, active user, and health. |

### 🔗 Easy Spotify Pairing via TeamSpeak Chat

No VNC, terminal access, or SSH port forwarding is required to link or switch Spotify accounts:
1. Make sure your bot container is running (`docker compose up -d bot1`).
2. In the TeamSpeak channel chat, type **`!login`** (or **`!pair`**).
3. The bot immediately replies with a Spotify pairing link: `https://spotify.com/pair?code=XXXXXX`.
4. Open the link on any phone or browser, log in to your Spotify Premium account, and click **Pair / Confirm**.
5. Within seconds, the bot automatically links and announces in chat:
   `✅ Spotify Connected! Successfully paired as <username>. Ready to play music!`
6. If your subscription ever expires or you want to switch accounts, anyone with the music role can type `!login` (or an admin can type `!login force` or `!logout`).

### 🔑 Step-by-Step Spotify Search Keys Wizard (`!spotifykeys`)

By default, the bot includes a shared search key so you can search songs (`!play song name`) immediately without signing up for anything.
- If the shared key ever reaches Spotify's rate limit, you can always paste **direct Spotify song/playlist links** with zero restrictions.
- Or, you can connect your own free developer keys right from TeamSpeak chat in 3 simple steps:
  1. Type **`!spotifykeys`** in chat. The bot gives you a link to `developer.spotify.com/dashboard`.
  2. Reply **`!spotifykeys ready`** when you have created an app.
  3. Paste your **Client ID**, then paste your **Client Secret**.
  4. The bot automatically tests and verifies the credentials with Spotify, saves them permanently, and activates your dedicated quota!
  *(To revert to the built-in default keys anytime, simply type `!spotifykeys reset`).*

### Role-Based Access Control (RBAC)

In your `.env.common` or `bots/bot1.env`, you can configure permissions by TeamSpeak Server Groups (roles):

```env
# Server Group IDs that have Admin access (!status, !restart, !audio, etc.)
ADMIN_SERVER_GROUPS=6

# Server Group IDs allowed to play music (!play, !queue, !skip, etc.)
# Leave empty to allow anyone in the channel to play music.
ALLOWED_SERVER_GROUPS=15,20

# Optional: Specific user UIDs who always have admin rights
ADMIN_UIDS=e8Y8...=
```
> [!TIP]
> Type `!myroles` in TeamSpeak channel chat at any time to see your current Server Group IDs!

---

## 👥 Scaling: Adding More Bots

Running multiple bots is as simple as:

1. Copy `bots/bot1.example.env` to `bots/bot2.env` with a unique `TS_NICK` and `SPOTIFY_DEVICE_NAME`.
2. Uncomment or add the `bot2` service in `docker-compose.yml`.
3. Launch with `docker compose up -d bot2` and type `!login` in chat to pair its Spotify account!
