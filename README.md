<div align="center">

# 🎵 TeamSpeak Spotify Bot (Dockerized)

**A high-performance, containerized TeamSpeak 3 Spotify Connect music bot.**

[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python)](https://python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## 💻 System Requirements

You can run this bot directly on your everyday PC or laptop for gaming sessions, or host it 24/7 on an affordable Linux VPS!

| Component | Local PC (Gaming / Party) | 24/7 Cloud VPS (Hosting Online) |
|---|---|---|
| **Operating System** | Windows 10/11 (with WSL2), macOS, or Linux | Ubuntu 22.04 / 24.04 LTS, Debian 12, or any Linux |
| **Processor (CPU)** | 1 Core (1.5 GHz+) | 1 vCPU (Hetzner, DigitalOcean, Oracle Cloud, etc.) |
| **Memory (RAM)** | 1 GB free RAM | 1 GB RAM (512MB + swap also supported) |
| **Disk Space** | 2 GB free disk space | 3 GB free disk space |
| **Network** | Stable broadband internet | Any VPS with public internet access |
| **Software** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Docker & Docker Compose (auto-installed by `install.sh`!) |
| **Accounts** | 1x Spotify Premium Account | 1x Spotify Premium Account |

> [!TIP]
> **Audio Quality:** Set your TeamSpeak music channel's audio codec to **Opus Music** with quality set to **10** (in Channel Edit Settings) for crystal-clear 320kbps streaming!

---

## ☁️ Beginner Guide: 24/7 Cloud Hosting (VPS / Dedicated Server)

Want your music bot running 24/7 without keeping your personal computer turned on? Rent any affordable Linux VPS ($2–$4/month from Hetzner, DigitalOcean, Linode, OVH, or Oracle Cloud Free Tier) running Ubuntu 22.04 or 24.04 LTS.

### ⚡ Method A: The 1-Command All-in-One Installer (Recommended)

You don't need to manually install Docker, edit configuration files with nano, or configure containers. Run this single command in your VPS terminal:

```bash
git clone https://github.com/mohammed-Araf/TS-Music-Bot.git && cd TS-Music-Bot && bash install.sh
```

#### 💡 Can I configure it directly inside the script?
**Yes!** If you prefer editing files over interactive terminal prompts, you can simply open `install.sh` in any text editor and customize the settings at the top of the file:
```bash
# ⚙️ CONFIGURATION SETTINGS (at the top of install.sh)
TS_HOST="ts.example.com"          # Your TeamSpeak server IP or domain
TS_PORT="9987"                    # TeamSpeak server port (default: 9987)
TS_CHANNEL="Music"                # Target channel name
TS_NICK="MusicBot1"               # Bot nickname in TeamSpeak
```
Then run `bash install.sh -y` to auto-deploy with your saved settings!

#### 🤖 What `install.sh` does automatically:
1. **Checks Docker:** If Docker is already installed, it skips installation. If missing, it installs the official Docker Engine and Compose plugin automatically.
2. **Checks / Overwrites Configuration:** Prompts you for your server details (or uses the values from the top of the script) and generates `.env.common` and `bots/bot1.env`.
3. **Downloads Missing Dependencies:** Automatically prepares data directories and builds the container image locally.
4. **Starts the Bot:** Launches the container in the background (`docker compose up -d bot1`).

---

### 🛠️ Method B: Step-by-Step Manual Setup

If you prefer configuring everything manually:

#### Step 1: Connect to your VPS and Install Docker
```bash
# SSH into your VPS
ssh root@your_vps_ip

# Install Docker
curl -fsSL https://get.docker.com | sh
```

#### Step 2: Clone the Repository
```bash
git clone https://github.com/mohammed-Araf/TS-Music-Bot.git
cd TS-Music-Bot
```

#### Step 3: Configure Settings
```bash
# Copy example configuration templates
cp .env.common.example .env.common
cp bots/bot1.example.env bots/bot1.env

# Edit server details
nano .env.common
```
Fill in your `TS_HOST`, `TS_PORT`, and `TS_CHANNEL`. Press `Ctrl+O` then `Enter` to save, and `Ctrl+X` to exit.

#### Step 4: Start the Bot
```bash
docker compose up -d bot1
```

---

### 🔗 Pairing Spotify on VPS (Zero GUI / No VNC Required!)

Once the bot starts on your VPS:
1. Join your TeamSpeak server and enter the music channel.
2. In the channel chat, type:
   ```text
   !login
   ```
3. The bot will send you a pairing link: `https://spotify.com/pair?code=XXXXXX`.
4. Open the link on your phone or PC browser, log in to Spotify Premium, and tap **Pair**.
5. The bot connects immediately and is ready to stream 24/7!

---

### 🛡️ VPS Maintenance & Management Commands

| Action | Command |
|---|---|
| **View live logs** | `docker compose logs -f bot1` |
| **Restart the bot** | `docker compose restart bot1` |
| **Stop the bot** | `docker compose down` |
| **Start the bot** | `docker compose up -d bot1` |
| **Reconfigure settings** | `bash install.sh` |

> [!NOTE]
> **Auto-Start on Reboot:** The container is configured with `restart: unless-stopped`. If your VPS reboots, the music bot will automatically start itself back up without you having to log into SSH!

---

## 🎮 Beginner Guide: Run Locally on Your PC (No Hosting Needed)

Want to play music with your friends in TeamSpeak right now without renting a cloud server? Follow these simple steps:

### Step 1: Install Docker Desktop on your PC
1. Download **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** for your operating system (Windows, Mac, or Linux).
2. Install it (on Windows, leave the default checkbox **"Use WSL 2 instead of Hyper-V"** enabled).
3. Open Docker Desktop and wait until the whale icon in the bottom corner turns green/steady.

### Step 2: Download This Bot
1. Click the green **`< > Code`** button at the top of this GitHub page and select **Download ZIP** (or run `git clone https://github.com/mohammed-Araf/TS-Music-Bot.git`).
2. Extract the downloaded ZIP file to any folder on your computer (e.g. `Downloads` or `Desktop`).

### Step 3: Quick Configuration (Just 3 Lines!)
1. Inside the bot folder, find `.env.common.example` and rename or copy it to **`.env.common`**.
2. Find `bots/bot1.example.env` and rename or copy it to **`bots/bot1.env`**.
3. Open **`.env.common`** with Notepad or any text editor and fill in your TeamSpeak details:
   ```env
   TS_HOST=your.teamspeak.server.com
   TS_PORT=9987
   TS_CHANNEL=Music
   ```
   *(Optional: If your channel has a password, enter `TS_CHANNEL_PASSWORD=yourpass`)*.
4. *(Optional)* In `bots/bot1.env`, you can change `TS_NICK=MyMusicBot` to your preferred bot nickname. Save and close the files.
*(Mac / Linux users can also simply double-click or run `bash install.sh` to configure and start automatically!)*

### Step 4: Start the Bot
Open your terminal (Command Prompt, PowerShell, or macOS Terminal) inside the bot folder, and run:
```bash
docker compose up -d bot1
```
Docker will automatically build the container image and start the bot. Within seconds, you will see the bot join your TeamSpeak channel!

### Step 5: Connect Spotify and Play!
1. In your TeamSpeak channel chat, type:
   ```text
   !login
   ```
2. The bot will reply with a Spotify pairing link (e.g. `https://spotify.com/pair?code=XXXXXX`).
3. Click the link on your phone, tablet, or browser, log in to Spotify Premium, and tap **Confirm / Pair**.
4. The bot will automatically announce in TeamSpeak:
   ```text
   ✅ Spotify Connected! Successfully paired as <username>. Ready to play music!
   ```
5. You can now immediately play any song or playlist:
   ```text
   !play Bohemian Rhapsody
   ```

---

### 🕹️ How to Turn On & Turn Off the Bot Anytime

- **To turn off the bot:** Open your terminal in the bot folder and run:
  ```bash
  docker compose down
  ```
- **To turn on the bot for your next party:**
  ```bash
  docker compose up -d bot1
  ```
  *(Spotify credentials stay saved permanently on your computer, so you won't have to log in every time!)*

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
| `!spotifykeys` | Allowed Role / Admin | Step-by-step wizard to connect custom free Spotify search keys. |
| `!myroles` | Everyone | View your current UID, Server Group IDs, and Channel Group ID. |
| `!help` | Everyone | Show list of available commands. |
| `!logout` | Admin | Unlink currently paired Spotify account. |
| `!restart` | Admin | Restart the container process. |
| `!reconnect` | Admin | Reconnect TeamSpeak 3 client to the channel. |
| `!audio` | Admin | Restart `go-librespot` audio engine. |
| `!status` | Admin | Check Spotify connection status, active user, and health. |

---

### 🔗 Easy Spotify Pairing via TeamSpeak Chat

No VNC, terminal access, or SSH port forwarding is required to link or switch Spotify accounts:
1. Make sure your bot container is running (`docker compose up -d bot1`).
2. In the TeamSpeak channel chat, type **`!login`** (or **`!pair`**).
3. The bot immediately replies with a Spotify pairing link: `https://spotify.com/pair?code=XXXXXX`.
4. Open the link on any phone or browser, log in to your Spotify Premium account, and click **Pair / Confirm**.
5. Within seconds, the bot automatically links and announces in chat:
   `✅ Spotify Connected! Successfully paired as <username>. Ready to play music!`
6. If your subscription ever expires or you want to switch accounts, anyone with the music role can type `!login` (or an admin can type `!login force` or `!logout`).

---

### 🔑 Step-by-Step Spotify Search Keys Wizard (`!spotifykeys`)

By default, the bot includes a shared search key so you can search songs (`!play song name`) immediately without signing up for anything.
- If the shared key ever reaches Spotify's rate limit, you can always paste **direct Spotify song/playlist links** with zero restrictions.
- Or, you can connect your own free developer keys right from TeamSpeak chat in 3 simple steps:
  1. Type **`!spotifykeys`** in chat. The bot gives you a link to `developer.spotify.com/dashboard`.
  2. Reply **`!spotifykeys ready`** when you have created an app.
  3. Paste your **Client ID**, then paste your **Client Secret**.
  4. The bot automatically tests and verifies the credentials with Spotify, saves them permanently, and activates your dedicated quota!
  *(To revert to the built-in default keys anytime, simply type `!spotifykeys reset`).*

---

### 🛡️ Role-Based Access Control (RBAC)

In your `.env.common` or `bots/bot1.env`, you can configure permissions by TeamSpeak Server Groups (roles):

```env
# Server Group IDs that have Admin access (!status, !restart, !audio, etc.)
ADMIN_SERVER_GROUPS=6

# Server Group IDs allowed to play music (!play, !queue, !skip, etc.)
# Leave empty to allow anyone in the channel to play music.
ALLOWED_SERVER_GROUPS=50

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
