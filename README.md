# TeamSpeak 3 Spotify Music Bot

An ultra-lightweight, streaming-only TeamSpeak 3 music bot optimized for Linux/macOS environments (such as VPS instances). It plays music directly from Spotify Premium using `ncspot` or the official Spotify client, routed through a PulseAudio virtual loopback device directly into the official TeamSpeak 3 desktop client.

> [!IMPORTANT]
> This bot does **never download tracks**. It streams audio in real-time, resulting in minimal CPU usage (<15% when playing) and memory overhead, making it ideal for 1 GB RAM VPS environments.

---

## Key Features

* **Legitimate Spotify Streaming**: Streams music directly from Spotify Premium (using the Spotify API for metadata and `ncspot` as the backend player).
* **Smart Command Routing**:
  * **`!p <query>`**: Automatically plays a search query or link immediately if the queue is stopped.
  * **`!play <query>`**: Queues the track if a song is currently playing.
  * **Dynamic Selection**: Both commands dynamically route based on active playback state so users get expected behavior (instant play vs. queue addition).
* **Spotify Search Defaults**: Plain text search queries (e.g. `!p Alan Walker Faded`) automatically resolve to a Spotify search (`sp track ...`) without needing explicit prefixes.
* **Custom Command Configuration**: Supports mapping any command to a custom trigger name and prefix via a configuration file.
* **Multi-Service Support**: Streams Spotify natively, and supports SoundCloud, YouTube, and Bandcamp playbacks via `mpv` routing.
* **Pre-Shuffling**: Allows shuffling albums and playlists before adding them to the queue to avoid shuffling the entire playback history.

---

## Architecture Flow

```mermaid
graph TD
    User["TeamSpeak Channel Chat"] -->|!p Alan Walker Faded| BotJar["TS3 MusicBot (Java/Kotlin)"]
    BotJar -->|Parse & Preprocess| BotJar
    BotJar -->|Spotify Web API| Metadata["Fetch track link"]
    BotJar -->|MPRIS / D-Bus| Ncspot["ncspot (Spotify Premium Player in tmux)"]
    Ncspot -->|Plays Stream| PulseAudio["PulseAudio Loopback Device"]
    PulseAudio -->|Capture Monitor| TS3Client["TS3 Desktop Client (running inside Xvfb)"]
    TS3Client -->|Transmit Voice| TS3Server["TeamSpeak 3 Server Channel"]
```

---

## Dependencies & Prerequisites

To run this bot (GUI-controller mode), your server/host machine requires:

* **Java Runtime**: JDK 17 or higher.
* **OpenJFX**: JavaFX platform libraries (typically `/usr/share/openjfx/lib`).
* **PulseAudio**: Virtual loopback device for capturing system output.
* **Xvfb**: X Virtual Framebuffer (to run the GUI TeamSpeak 3 client headlessly on headless servers).
* **tmux**: Terminal multiplexer to run `ncspot` in a background workspace.
* **ncspot**: A ncurses-based Spotify client (requires a Spotify Premium subscription).
* **TeamSpeak 3 Client**: Official desktop client (Linux amd64).

---

## Configuration Files

### 1. Bot Settings (`ts3-musicbot.config`)
Configure connection settings, paths, and player options.
Example options:
```ini
# Server connection
serverAddress=172.105.53.24
serverPort=9987
channelPath=[cspacer53] ★★★ RAGE Gamers ★★★/🎵 Music & Chill
channelPassword=1234
botNickname=Alan's MusicBot

# Spotify credentials & player selection
spotifyPlayer=ncspot
spotifyUsername=your_username
spotifyPassword=your_password
```

### 2. Custom Commands (`commands.config`)
Modify this file to customize prefixes and command bindings. The default configured mapping is:
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
```

### 3. User Permissions Configuration (`permissions.yml`)
Enable badge-based validation for controlling commands and specify which commands are publicly accessible:
```yaml
permissions:
  # Enable or disable the entire permissions module
  enabled: true

  # List of badges required to execute restricted/music control commands
  required_badges:
    - "music_access"
    - "vip"
    - "admin"

  # Cache badges locally to prevent querying the TS3 server on every command
  cache_badges: true
  cache_ttl_seconds: 300

  # Message sent to the channel when a user attempts a restricted command without permission
  deny_message: "You are not allowed to use music commands."

  # Commands that can be executed by anyone, regardless of badges/groups
  public_commands:
    - "np"
    - "q"
    - "src"
    - "ping"
```

> [!TIP]
> **Badge IDs vs Server Group IDs**:
> - `required_badges` accepts **String** values (keys/GUIDs) of badges (e.g. `"vip"`, `"admin"`, `"music_access"`).
> - `required_server_groups` accepts **Integer** IDs of TeamSpeak server groups (e.g. `10`, `20`).

---

## Starting the Bot

To start the environment, load the D-Bus session, spin up PulseAudio/Xvfb, and run the JAR with configs, execute the startup script `run-bot.sh`:

```bash
#!/bin/bash
set -e

# Setup User D-Bus session environment (required for ncspot MPRIS controls)
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

# Initialize PulseAudio
pulseaudio --check || pulseaudio --start --exit-idle-time=-1
sleep 2

# Spawn virtual display frame on display :99 for TS3 GUI
Xvfb :99 -screen 0 1024x768x24 &
sleep 2
export DISPLAY=:99

# Run the Bot with Config overrides
java --module-path /usr/share/openjfx/lib \
     --add-modules javafx.controls,javafx.fxml \
     -jar ts3-musicbot.jar \
     --config ts3-musicbot.config \
     --command-config commands.config
```

---

## Commands Reference

The following commands are available inside the channel chat where the bot is connected (using the `!` prefix as mapped in `commands.config`):

| Command | Arguments | Description |
| :--- | :--- | :--- |
| **`!p`** | `<query / link>` | Smart Play: Plays track immediately if idle (translated to `queue-playnow`). Defaults plain text queries to Spotify. |
| **`!play`** | `<query / link>` | Smart Queue: Appends track to the queue if playing (translated to `queue-add`). Defaults plain text queries to Spotify. |
| **`!s`** | None | Skips the current track in the queue. |
| **`!stop`** | None | Stops queue and clears active playback. |
| **`!pause`** | None | Pauses playback. |
| **`!r`** | None | Resumes playback. |
| **`!q`** | None | Lists the next 15 tracks in the queue. |
| **`!c`** | None | Clears all tracks from the queue. |
| **`!rm`** | `<position>` | Deletes the track at the specified index (0-indexed). |
| **`!mv`** | `<from> -p <to>` | Moves a track from index `<from>` to index `<to>`. |
| **`!v`** | `<0-100>` | Sets playback volume. |
| **`!loop`** | `<amount>` | Queues the currently playing track `<amount>` times. |
| **`!np`** | None | Displays detailed information about the currently playing song. |
| **`!src`** | `<query / link>` | Displays source/metadata information for a search query. |

---

## Deploying as a systemd Service (VPS)

You can run the bot persistently in the background on your VPS using systemd.

1. Create a service file `/etc/systemd/system/ts3-musicbot.service`:
```ini
[Unit]
Description=TeamSpeak 3 Music Bot (Alan's Music bot Alpha)
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

2. Reload systemd daemon and start/enable the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ts3-musicbot
sudo systemctl start ts3-musicbot
```

3. Monitor logs in real-time:
```bash
sudo journalctl -u ts3-musicbot -f -n 100
```

---

## TeamSpeak Channel Description BBCode Template

You can copy and paste the BBCode layout below directly into the description of your TeamSpeak music channel to provide a clean commands layout for users:

```bbcode
[center][b][size=16][color=#FF8C00]🎵 ALAN'S MUSIC BOT 🎵[/color][/size][/b]
[color=#888888]Premium head-in-process music streaming engine[/color][/center]
[hr]
[b][color=#00BFFF]ℹ️ Info:[/color][/b] Everyone can use [b]![/b] commands. Use play command ([i]!p[/i]) with a song name or Spotify/YouTube URL.

[table]
[tr]
[td][b][color=#FF8C00]Command[/color][/b]   [/td]
[td][b][color=#FF8C00]Alias[/color][/b]   [/td]
[td][b][color=#FF8C00]Usage / Example[/color][/b]   [/td]
[td][b][color=#FF8C00]Description[/color][/b][/td]
[/tr]
[tr]
[td][b]!play[/b][/td]
[td]!p[/td]
[td][i]!p dil[/i] or [i]!p spotify_url[/i][/td]
[td]Play or queue a song (Spotify/YT/SC)[/td]
[/tr]
[tr]
[td][b]!skip[/b][/td]
[td]!s[/td]
[td][i]!s[/i][/td]
[td]Skip the current playing song[/td]
[/tr]
[tr]
[td][b]!nowplaying[/b][/td]
[td]!np[/td]
[td][i]!np[/i][/td]
[td]Show current playing song details[/td]
[/tr]
[tr]
[td][b]!queue[/b][/td]
[td]!q[/td]
[td][i]!q[/i][/td]
[td]Print the list of queued songs[/td]
[/tr]
[tr]
[td][b]!volume[/b][/td]
[td]!v[/td]
[td][i]!v 50[/i] or [i]!v +15[/i][/td]
[td]Adjust bot volume (0-100)[/td]
[/tr]
[tr]
[td][b]!pause[/b][/td]
[td]!pause[/td]
[td][i]!pause[/i][/td]
[td]Pause song playback[/td]
[/tr]
[tr]
[td][b]!resume[/b][/td]
[td]!r[/td]
[td][i]!r[/i][/td]
[td]Resume paused playback[/td]
[/tr]
[tr]
[td][b]!loop[/b][/td]
[td]!loop[/td]
[td][i]!loop[/i] or [i]!loop queue[/i][/td]
[td]Loop current song / entire queue[/td]
[/tr]
[tr]
[td][b]!clear[/b][/td]
[td]!c[/td]
[td][i]!c[/i][/td]
[td]Clear all queued songs[/td]
[/tr]
[tr]
[td][b]!remove[/b][/td]
[td]!rm[/td]
[td][i]!rm 3[/i][/td]
[td]Remove song at index from queue[/td]
[/tr]
[tr]
[td][b]!move[/b][/td]
[td]!mv[/td]
[td][i]!mv 3 1[/i][/td]
[td]Move song in queue from position A to B[/td]
[/tr]
[tr]
[td][b]!sources[/b][/td]
[td]!src[/td]
[td][i]!src[/i][/td]
[td]Check status of music providers[/td]
[/tr]
[tr]
[td][b]!join[/b][/td]
[td]!join[/td]
[td][i]!join Music Room[/i][/td]
[td]Move bot to a different channel[/td]
[/tr]
[tr]
[td][b]!ping[/b][/td]
[td]!ping[/td]
[td][i]!ping[/i][/td]
[td]Verify bot connection latency[/td]
[/tr]
[/table]
[hr]
[center][color=#888888]💡 Tip: Keep search terms simple (e.g. "Artist - Track") for best results.[/color][/center]
```
