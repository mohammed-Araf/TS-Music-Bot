# TeamSpeak 3 Music Bot 🎵

An ultra-lightweight, high-performance, and completely headless TeamSpeak 3 music bot. Rebuilt from the ground up to run directly in-process with no external dependencies (no `mpv`, no `PulseAudio`, no native desktop players required). 

Optimized to run seamlessly on low-cost virtual servers targeting **1 vCPU** and **1 GB RAM** constraints.

---

## 🚀 Key Features

*   **Direct Audio Streaming**: Interaces directly with TeamSpeak using `ts3j`'s native voice connection API. Audio frames are encoded to Opus on-the-fly and streamed directly to the channel.
*   **Zero External Dependencies**: Operates completely headless in-process. No PulseAudio loopbacks, no X11/GUI servers, and no subprocess spawning.
*   **Multi-Provider Failover Chain**:
    *   **Spotify**: Metadata matching resolves track/artist information using the Spotify Web API.
    *   **SoundCloud**: Primary high-quality stream source via LavaPlayer.
    *   **YouTube**: Secondary fallback stream source using the native Youtube-Plugin.
*   **Low Memory Footprint**: Uses a serial garbage collector (`-XX:+UseSerialGC`), tiny audio buffers (20ms), and worker thread constraints to maintain a memory footprint under **200 MB** at idle and **400 MB** during active playback.
*   **Flexible Access Control**: Supports TeamSpeak badge-based GUID authorization AND server group permissions checks, paired with a thread-safe TTL cache.
*   **Dynamic Customization**: Fully configurable command prefixes, custom aliases, and volumes.

---

## 🛠️ Requirements

*   **Java Runtime Environment (JRE)**: Java 21 or higher.
*   **TeamSpeak 3 Server**: Access to a TS3 server and permission to join voice channels.
*   **API Credentials**:
    *   **Spotify Web API**: A Client ID and Client Secret (retrieve for free from the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)).
    *   **YouTube Data API**: An API Key (obtain from the [Google Cloud Console](https://console.cloud.google.com/)).

---

## 📦 Setup & Installation

### 1. Compile the Application
Ensure you have Java 21 installed, then compile the executable shadow (fat) JAR:
```bash
./gradlew shadowJar
```
This packages all code, dependencies, and native encoders into a single file at `app/build/libs/ts3-musicbot.jar` (approx. 45 MB).

### 2. Prepare Configurations
Copy the template example configuration files to their active locations:
```bash
cp config.example.yml config.yml
cp providers.example.yml providers.yml
```

### 3. Configure Your Files

#### `config.yml`
Configure connection details and performance parameters:
```yaml
server:
  address: "127.0.0.1"      # TeamSpeak server IP
  port: 9987                 # TS3 UDP Port
  password: ""               # TS3 Server password (if any)
bot:
  nickname: "MusicBot"       # Display nickname in channel
  default_channel_id: 0      # Channel ID to join (set 0 to use name-based join)
  reconnect: true
  auto_join: true
  channel_name: "Music & Chill" # Channel path (e.g. "Lobby/Music Room")
  channel_password: ""       # Channel password (if any)
```

#### `providers.yml`
Input your credentials for Spotify, SoundCloud, and YouTube API:
```yaml
spotify:
  client_id: "YOUR_SPOTIFY_CLIENT_ID"
  client_secret: "YOUR_SPOTIFY_CLIENT_SECRET"
soundcloud:
  client_id: "YOUR_SOUNDCLOUD_CLIENT_ID"
youtube:
  api_key: "YOUR_YOUTUBE_API_KEY"
```

#### `permissions.yml`
Define badge and server group permissions. You can configure commands to be fully public or restricted.
```yaml
permissions:
  enabled: false             # Set to true to enforce badge/group authorization
  required_badges: []        # List of TeamSpeak badge GUIDs allowed to run admin commands
  required_server_groups: [] # List of server group IDs allowed to run admin commands
  cache_ttl_seconds: 300     # TTL cache for user permissions
  public_commands:           # Commands everyone can execute
    - "np"
    - "q"
    - "ping"
```

#### `commands.yml`
Configure custom command prefixes and short aliases:
```yaml
prefix: "!"
commands:
  play: "p"
  skip: "s"
  stop: "stop"
  pause: "pause"
  resume: "r"
  queue: "q"
  volume: "v"
  loop: "loop"
  nowplaying: "np"
```

---

## ⚡ Running the Bot

Run the bot with optimization flags designed for low memory and headless environments:

```bash
java -XX:+UseSerialGC -jar app/build/libs/ts3-musicbot.jar
```

> [!TIP]
> **Use Serial GC**: The `-XX:+UseSerialGC` flag tells the JVM to use a single-threaded Garbage Collector, which significantly reduces CPU overhead and RAM usage on single-core Virtual Private Servers (VPS).

---

## 🎮 Commands List

All commands use the prefix defined in `commands.yml` (default `!`).

| Command | Alias | Argument | Description |
| :--- | :--- | :--- | :--- |
| `!play` | `!p` | `<query \| URL>` | Search and play a song/playlist from Spotify, YouTube, or SoundCloud. |
| `!skip` | `!s` | None | Skip the current playing track. |
| `!stop` | `!stop` | None | Stop playback, clear the queue, and make the bot idle. |
| `!pause` | `!pause`| None | Pause current playback. |
| `!resume`| `!r` | None | Resume paused playback. |
| `!queue` | `!q` | None | Print current track queue. |
| `!volume`| `!v` | `<0-100 \| +/-diff>` | View current volume or set absolute/relative volume level. |
| `!loop`  | `!loop` | `[queue]` | Toggle track looping (or queue looping if `queue` is specified). |
| `!nowplaying` | `!np` | None | Print the title, artist, and URL of the current playing track. |
| `!sources` | `!src` | None | Lists status of available music providers (Spotify, SoundCloud, YouTube). |
| `!ping`  | `!ping` | None | Check latency/health status. |

---

## 🛠️ Troubleshooting & Logs

- **Audio Distortion / High Speed Playback**: Checked and resolved by ensuring byte order compatibility in the PCM pipeline. Standardized output settings in LavaPlayer match your system's native architecture (`LITTLE_ENDIAN`).
- **NPE on Headless Background Start**: The bot implements a buffered stdin loop (`BufferedReader(InputStreamReader(System.in))`) instead of `System.console()` to ensure background terminal processes don't throw null pointer exceptions on startup.
- **Provider Failures**: If a search query fails, the bot will automatically fall back:
  `Spotify -> SoundCloud -> YouTube`. If YouTube encounters consecutive quota failures (e.g. HTTP 403), the YouTube search provider is dynamically disabled to prevent lockups.

---

## ⚖️ License
Distributed under the GNU General Public License v3 (GPLv3). See [LICENSE](file:///Users/araf/Documents/Projects/ts3-musicbot-master/LICENSE) for more information.
