# TS Spotify Bot: Complete Build Spec

One Docker image. One container = one bot. Each bot has its own Spotify Premium account, joins a TeamSpeak server as a normal client, reads `!commands` from channel chat, and plays Spotify audio into the channel.

> **Status of this document:** a design and reference implementation. The code has **not been run against a real TS server or Spotify account**. Everything in section 14 ("Verify before you trust it") is something I'm not 100% sure about and you should check first. Where I say "verify", I mean it.

---

## 1. What you are building

```
Chat command (!play ...) ──► Controller ──► go-librespot (Spotify Connect device)
                                                  │ audio
                                                  ▼
                                      PulseAudio null sink "music"
                                                  │ monitor
                                                  ▼
                            Headless TeamSpeak 3 client ──► TS server voice channel
```

Why this design:
- **No yt-dlp, no proxies, no YouTube.** Spotify limits are per account, not per IP, so N bots with N accounts don't starve each other.
- **TeamSpeak's ServerQuery cannot send audio.** The bot must be a real client, so we run the real Linux TS client headless (Xvfb) and feed it audio from a virtual microphone.
- **go-librespot** is a Spotify Connect receiver with a local HTTP API, so we control playback without depending on Spotify's restricted Web API (we only use the Web API for *search*).

---

## 2. Reality check (read before building)

| Issue | Detail |
|---|---|
| **Spotify ToS** | Using Spotify to play to a voice channel is against their terms. Account bans are possible. Use dedicated accounts, never your main one. Keep to a private server. |
| **Premium required** | Free accounts do not work with librespot. One **individual** Premium account per bot (no sharing, because Spotify allows one active stream per account). |
| **Image distribution** | The image bundles the TeamSpeak client, whose license may restrict redistribution. Build locally and do **not** push the image to a public registry. |
| **TeamSpeak version** | This spec targets the **TS3 Linux client (3.6.x)** plus its ClientQuery plugin. Check your server's version and whether the client is compatible (see section 14). TeamSpeak 6 may change this. |
| **Identity security level** | Servers can require a minimum identity security level. A fresh identity may need upgrading (takes time) before the server accepts it. Ask the server admin. |
| **Not zero-maintenance** | Expect to rebuild the image every few months when Spotify, go-librespot, or TeamSpeak changes something. |
| **x86_64 only** | The TS3 Linux client is amd64 only. Build with `--platform linux/amd64` (on an M3 MacBook that means emulation, so use it for testing only, and run production on an x86 VPS). |

---

## 3. Tech stack (everything inside the image)

| Layer | Component | Purpose | Version policy |
|---|---|---|---|
| OS | Debian 12 (`bookworm-slim`) | Base image, glibc for the TS client | pin tag |
| Virtual display | `xvfb` | Headless X server for the TS GUI client | distro |
| Remote setup | `x11vnc` | One-time GUI setup (license, plugin, identity). Disabled in normal runs | distro |
| Audio server | `pulseaudio` + `pulseaudio-utils` | Two null sinks: `music` (Spotify out, TS in) and `void` (TS out) | distro |
| Spotify receiver | **go-librespot** (Go binary) | Spotify Connect device + HTTP/WebSocket API | **pin a release** |
| Voice client | **TeamSpeak 3 Linux client** `3.6.x` | Joins the server, transmits the `music` monitor | pin + sha256 |
| TS control | **ClientQuery plugin** (bundled) | Local TCP API (`127.0.0.1:25639`) for chat events and text replies | bundled |
| Controller | **Python 3.11** (Debian default), `asyncio`, `aiohttp` | Command parsing, permissions, Spotify calls, health | pin in `requirements.txt` |
| Supervision | `supervisor` | Runs 5 to 6 processes in one container, restarts crashes | distro |
| Utilities | `curl`, `socat`, `gettext-base` (envsubst), `sqlite3`, `procps` | Healthcheck, setup-mode port forward, config rendering, debugging | distro |
| Orchestration | Docker Compose v2 | N bots = N services | n/a |
| Self-healing | `willfarrell/autoheal` container | Restarts containers whose healthcheck fails | optional |

Why run several processes in one container: the TS client, the audio server, and the Spotify receiver must share one PulseAudio instance and one X display. Splitting them is possible but adds networked audio plumbing. One supervised container per bot is the simplest thing that works.

---

## 4. Repository layout

```
ts-spotify-bot/
├─ Dockerfile
├─ docker-compose.yml
├─ .env.common                  # shared settings (server host, prefix, etc.)
├─ bots/
│  ├─ bot1.env                  # per-bot settings (nickname, apikey, admin uids)
│  └─ bot2.env
├─ data/                        # per-bot persistent volumes (git-ignored)
│  ├─ bot1/
│  └─ bot2/
├─ docker/
│  ├─ entrypoint.sh
│  ├─ supervisord.conf
│  ├─ pulse.pa
│  ├─ run-ts3.sh
│  └─ go-librespot.config.tmpl.yml
├─ controller/
│  ├─ requirements.txt
│  └─ bot/
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ config.py
│     ├─ tsescape.py
│     ├─ clientquery.py
│     ├─ spotify.py
│     ├─ commands.py
│     └─ app.py
├─ .gitignore                   # data/, *.env with secrets
└─ README.md
```

Git hygiene (given how the last project went): put this in a **new repo or branch**, commit early, and `git tag v1-working` the moment it plays music in a channel.

---

## 5. Prerequisites

1. **VPS or machine**: x86_64, Linux, 2+ vCPU, about 1 GB RAM per bot (the TS client is the heavy part), Docker + Compose v2 installed.
2. **One Spotify Premium account per bot** (individual plans).
3. **A Spotify developer app** (free) at the Spotify developer dashboard, used only for track search with the client-credentials flow. Note its Client ID and Client Secret. Check the dashboard for current restrictions.
4. **TeamSpeak server access** with the admin's OK. Per bot you need:
   - Permission to join the channel and talk (`i_client_talk_power` at or above the channel's needed talk power).
   - Ideally `b_client_ignore_antiflood` so replies aren't throttled.
   - The target channel using the **Opus Music** codec at good quality, otherwise music sounds like a phone call.
5. **Each admin's TS unique ID** (UID) for the permission list (TS client: Tools > Identities, or right-click a user > Information).

---

## 6. Container files

### 6.1 `Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
FROM --platform=linux/amd64 debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

# ---- pinned versions (fill these in) ----
ARG TS3_VERSION=3.6.2
ARG TS3_SHA256=                       # first build: leave empty, copy the printed hash here
ARG GOLIBRESPOT_VERSION=vX.Y.Z        # check the go-librespot releases page and pin
ARG GOLIBRESPOT_ASSET=go-librespot_linux_x86_64.tar.gz   # verify asset name for that release

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl bzip2 xz-utils sqlite3 procps socat gettext-base \
      supervisor xvfb x11vnc \
      pulseaudio pulseaudio-utils libpulse0 libasound2 libasound2-plugins \
      libogg0 libvorbis0a libvorbisfile3 libflac12 \
      python3 python3-venv python3-pip \
      fonts-dejavu-core \
      libglib2.0-0 libnss3 libfontconfig1 libdbus-1-3 libegl1 libgl1 \
      libx11-xcb1 libxrender1 libxext6 libxi6 libxtst6 libxrandr2 libxss1 \
      libxcomposite1 libxcursor1 libxdamage1 libxkbcommon-x11-0 \
      libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
      libxcb-render-util0 libxcb-xkb1 libxcb-shape0 libxcb-randr0 \
      libxcb-xfixes0 libxcb-sync1 libxcb-shm0 libxcb-glx0 \
 && rm -rf /var/lib/apt/lists/*
# If the TS client fails to start, run `ldd /opt/ts3client/ts3client_linux_amd64 | grep "not found"`
# inside the container and add the missing packages above.

# ---- TeamSpeak 3 client ----
RUN curl -fsSL -o /tmp/ts3.run \
      "https://files.teamspeak-services.com/releases/client/${TS3_VERSION}/TeamSpeak3-Client-linux_amd64-${TS3_VERSION}.run" \
 && sha256sum /tmp/ts3.run \
 && ( [ -z "${TS3_SHA256}" ] || echo "${TS3_SHA256}  /tmp/ts3.run" | sha256sum -c - ) \
 && chmod +x /tmp/ts3.run \
 && /tmp/ts3.run --noexec --target /opt/ts3client \
 && rm /tmp/ts3.run

# ---- go-librespot ----
RUN curl -fsSL \
      "https://github.com/devgianlu/go-librespot/releases/download/${GOLIBRESPOT_VERSION}/${GOLIBRESPOT_ASSET}" \
    | tar -xz -C /usr/local/bin go-librespot \
 && chmod +x /usr/local/bin/go-librespot

# ---- user + dirs ----
# HOME lives in the volume so ~/.ts3client (settings, identity, plugin state) persists.
RUN useradd -m -u 1000 -d /data/home -s /bin/bash bot \
 && mkdir -p /data /opt/bot \
 && chown -R bot:bot /data

# ---- app ----
COPY docker/ /opt/bot/docker/
COPY controller/ /opt/bot/controller/
RUN chmod +x /opt/bot/docker/*.sh \
 && python3 -m venv /opt/bot/venv \
 && /opt/bot/venv/bin/pip install --no-cache-dir -r /opt/bot/controller/requirements.txt

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fs http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/opt/bot/docker/entrypoint.sh"]
```

### 6.2 `docker/entrypoint.sh`

```bash
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

# Render go-librespot config (state/credentials persist alongside it in /data/librespot)
envsubst < /opt/bot/docker/go-librespot.config.tmpl.yml > /data/librespot/config.yml
chown bot:bot /data/librespot/config.yml

exec /usr/bin/supervisord -n -c /opt/bot/docker/supervisord.conf
```

### 6.3 `docker/pulse.pa`

```
# Minimal PulseAudio config: no hardware, two null sinks, unix socket.
load-module module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse.sock

# Where Spotify plays. Its .monitor is the "microphone" the TS client captures.
load-module module-null-sink sink_name=music sink_properties=device.description=Music

# Where the TS client "plays" what it hears (discarded).
load-module module-null-sink sink_name=void sink_properties=device.description=Void

set-default-sink void
set-default-source music.monitor
```

### 6.4 `docker/run-ts3.sh`

```bash
#!/usr/bin/env bash
# Starts the TS3 client and auto-connects via a ts3server:// URL.
set -euo pipefail

enc() { python3 -c 'import sys,urllib.parse as u; print(u.quote(sys.argv[1], safe=""))' "$1"; }

URL="ts3server://${TS_HOST}?port=${TS_PORT}&nickname=$(enc "${TS_NICK}")"
[ -n "${TS_CHANNEL:-}" ]          && URL="${URL}&channel=$(enc "${TS_CHANNEL}")"
[ -n "${TS_SERVER_PASSWORD:-}" ]  && URL="${URL}&password=$(enc "${TS_SERVER_PASSWORD}")"
[ -n "${TS_CHANNEL_PASSWORD:-}" ] && URL="${URL}&channelpassword=$(enc "${TS_CHANNEL_PASSWORD}")"

echo "${URL}" > /tmp/ts_url      # used by the controller's !reconnect

export QT_X11_NO_MITSHM=1
cd /opt/ts3client
exec ./ts3client_runscript.sh "${URL}"
```

### 6.5 `docker/go-librespot.config.tmpl.yml`

```yaml
# Option names: verify against the docs of the go-librespot version you pin.
log_level: info
device_name: "${SPOTIFY_DEVICE_NAME}"
device_type: speaker

audio_backend: pulseaudio
audio_device: music          # PulseAudio sink name

bitrate: 320                 # Premium
volume_steps: 100
initial_volume: ${INITIAL_VOLUME}
normalisation_enabled: true

credentials:
  type: interactive          # OAuth login once; credentials then persist in /data/librespot
  interactive:
    callback_port: 8888

server:                      # local control API used by the controller
  enabled: true
  address: 127.0.0.1
  port: 3678
```

### 6.6 `docker/supervisord.conf`

```ini
[supervisord]
nodaemon=true
user=root
logfile=/dev/null
pidfile=/tmp/supervisord.pid

[unix_http_server]
file=/tmp/supervisor.sock
chmod=0770
chown=root:bot

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///tmp/supervisor.sock

; ---------- display + audio ----------
[program:xvfb]
command=Xvfb :99 -screen 0 1280x800x24 -nolisten tcp
user=bot
priority=10
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

[program:pulseaudio]
command=pulseaudio --daemonize=no --exit-idle-time=-1 --disable-shm=yes -n -F /opt/bot/docker/pulse.pa --log-target=stderr
user=bot
priority=20
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

; ---------- Spotify ----------
[program:go-librespot]
command=go-librespot --config_dir /data/librespot
user=bot
priority=30
startsecs=5
autorestart=true
environment=HOME="/data/home",PULSE_SERVER="unix:/tmp/pulse.sock",PULSE_SINK="music"
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

; ---------- TeamSpeak client ----------
[program:ts3client]
command=/opt/bot/docker/run-ts3.sh
user=bot
priority=40
startsecs=10
autorestart=true
environment=HOME="/data/home",DISPLAY=":99",PULSE_SERVER="unix:/tmp/pulse.sock"
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

; ---------- controller ----------
[program:controller]
command=/opt/bot/venv/bin/python -m bot
directory=/opt/bot/controller
user=bot
priority=50
autostart=%(ENV_CONTROLLER_AUTOSTART)s
autorestart=true
startsecs=5
environment=HOME="/data/home",PULSE_SERVER="unix:/tmp/pulse.sock"
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

; ---------- setup-mode only ----------
[program:vnc]
command=x11vnc -display :99 -forever -shared -rfbport 5900 -passwd %(ENV_VNC_PASSWORD)s
user=bot
autostart=%(ENV_SETUP_AUTOSTART)s
autorestart=true
priority=45
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

; go-librespot's OAuth callback listens on loopback inside the container; this re-exposes it.
[program:authproxy]
command=socat TCP-LISTEN:8889,fork,reuseaddr TCP:127.0.0.1:8888
user=bot
autostart=%(ENV_SETUP_AUTOSTART)s
autorestart=true
priority=35
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
```

---

## 7. Compose and environment

### 7.1 `docker-compose.yml`

```yaml
x-bot: &bot
  image: ts-spotify-bot:latest
  build: .
  platform: linux/amd64
  restart: unless-stopped
  init: true
  shm_size: "256mb"
  mem_limit: 1g
  stop_grace_period: 15s
  labels: ["autoheal=true"]

services:
  bot1:
    <<: *bot
    container_name: tsbot1
    env_file: [.env.common, bots/bot1.env]
    volumes: ["./data/bot1:/data"]

  bot2:
    <<: *bot
    container_name: tsbot2
    env_file: [.env.common, bots/bot2.env]
    volumes: ["./data/bot2:/data"]

  autoheal:
    image: willfarrell/autoheal:latest
    restart: unless-stopped
    environment: ["AUTOHEAL_CONTAINER_LABEL=autoheal"]
    volumes: ["/var/run/docker.sock:/var/run/docker.sock"]
```

Adding a bot = copy a service block, a new `bots/botN.env`, and a new `data/botN` volume.

### 7.2 `.env.common`

```env
TS_HOST=your.teamspeak.server
TS_PORT=9987
TS_CHANNEL=Music
TS_SERVER_PASSWORD=
TS_CHANNEL_PASSWORD=

CMD_PREFIX=!
CMD_COOLDOWN=1.5
MAX_VOLUME=80
INITIAL_VOLUME=40

SPOTIFY_CLIENT_ID=xxxxxxxx          # developer app, used for search only
SPOTIFY_CLIENT_SECRET=xxxxxxxx
```

### 7.3 `bots/bot1.env`

```env
TS_NICK=MusicBot1
SPOTIFY_DEVICE_NAME=MusicBot1
TS_CLIENTQUERY_APIKEY=               # filled in after first-time setup
ADMIN_UIDS=base64uid1=,base64uid2=   # comma-separated TS unique IDs
```

Keep `.env*` files out of git.

---

## 8. Controller (Python)

### 8.1 `controller/requirements.txt`

```
aiohttp>=3.9,<4
```

### 8.2 Protocol notes (ClientQuery)

- TCP `127.0.0.1:25639`. Lines end with `\n\r`. After connecting, the plugin sends a banner, then you authenticate: `auth apikey=<KEY>`.
- Each command is answered by zero or more data lines then `error id=0 msg=ok`.
- Register for chat events: `clientnotifyregister schandlerid=<id> event=notifytextmessage`. Get the id from `currentschandlerid`.
- Incoming chat event fields: `targetmode` (`1`=private, `2`=channel, `3`=server), `msg`, `invokerid`, `invokername`, `invokeruid`.
- Reply to the channel: `sendtextmessage targetmode=2 target=<your_cid> msg=<escaped>`.
- Escaping: `\` to `\\`, `/` to `\/`, space to `\s`, `|` to `\p`, and `\a \b \f \n \r \t \v`.
- URLs pasted into TS chat arrive wrapped in BBCode, like `[URL]https://...[/URL]`. Strip it.
- Ignore your own messages by comparing `invokerid` with your own `clid` (from `whoami`).
- Identify users by **`invokeruid`**, never by nickname (nicknames are spoofable).

### 8.3 `bot/config.py`

```python
import os
from dataclasses import dataclass

def _f(name, default): return float(os.environ.get(name, default))
def _i(name, default): return int(os.environ.get(name, default))

@dataclass(frozen=True)
class Config:
    prefix: str = os.environ.get("CMD_PREFIX", "!")
    cooldown: float = _f("CMD_COOLDOWN", 1.5)

    cq_host: str = "127.0.0.1"
    cq_port: int = 25639
    cq_apikey: str = os.environ.get("TS_CLIENTQUERY_APIKEY", "")

    admin_uids: frozenset = frozenset(
        u.strip() for u in os.environ.get("ADMIN_UIDS", "").split(",") if u.strip()
    )

    lr_url: str = "http://127.0.0.1:3678"
    sp_client_id: str = os.environ.get("SPOTIFY_CLIENT_ID", "")
    sp_client_secret: str = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

    max_volume: int = _i("MAX_VOLUME", 80)
    initial_volume: int = _i("INITIAL_VOLUME", 40)

    health_port: int = 8080

CFG = Config()
```

### 8.4 `bot/tsescape.py`

```python
import re

_TO_ESC = [("\\", "\\\\"), ("/", "\\/"), (" ", "\\s"), ("|", "\\p"),
           ("\a", "\\a"), ("\b", "\\b"), ("\f", "\\f"), ("\n", "\\n"),
           ("\r", "\\r"), ("\t", "\\t"), ("\v", "\\v")]
_FROM_ESC = {"\\": "\\", "/": "/", "s": " ", "p": "|", "a": "\a", "b": "\b",
             "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}

def escape(s: str) -> str:
    for raw, esc in _TO_ESC:          # backslash first, order matters
        s = s.replace(raw, esc)
    return s

def unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] in _FROM_ESC:
            out.append(_FROM_ESC[s[i + 1]]); i += 2
        else:
            out.append(c); i += 1
    return "".join(out)

def parse_line(line: str):
    """'notifytextmessage a=b c=d' -> ('notifytextmessage', {'a': 'b', 'c': 'd'})"""
    parts = line.strip().split(" ")
    name, fields = parts[0], {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            fields[k] = unescape(v)
        else:
            fields[p] = ""
    return name, fields

_BBCODE = re.compile(r"\[/?(?:URL|B|I|U|S|COLOR|SIZE|CODE|QUOTE)(?:=[^\]]*)?\]", re.I)

def strip_bbcode(s: str) -> str:
    return _BBCODE.sub("", s).strip()
```

### 8.5 `bot/clientquery.py`

```python
import asyncio, logging
from .tsescape import escape, parse_line

log = logging.getLogger("clientquery")

class QueryError(Exception):
    pass

class ClientQuery:
    def __init__(self, host, port, apikey, on_event):
        self.host, self.port, self.apikey = host, port, apikey
        self.on_event = on_event            # async callable(name, fields)
        self._r = self._w = None
        self._lock = asyncio.Lock()
        self._pending = None                # future for current command
        self._buf = []
        self._task = None
        self.connected = False

    async def connect(self):
        self._r, self._w = await asyncio.open_connection(self.host, self.port)
        self._task = asyncio.create_task(self._read_loop())
        await asyncio.sleep(0.5)            # let the banner arrive
        await self.cmd(f"auth apikey={self.apikey}")
        self.connected = True

    async def close(self):
        self.connected = False
        if self._task: self._task.cancel()
        if self._w:
            self._w.close()

    async def _read_loop(self):
        try:
            while True:
                raw = await self._r.readuntil(b"\n")
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                if line.startswith("notify"):
                    name, fields = parse_line(line)
                    asyncio.create_task(self.on_event(name, fields))
                elif line.startswith("error "):
                    _, f = parse_line(line)
                    if self._pending and not self._pending.done():
                        self._pending.set_result((list(self._buf), f))
                    self._buf.clear()
                else:
                    self._buf.append(line)
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.connected = False
            if self._pending and not self._pending.done():
                self._pending.set_exception(ConnectionError("ClientQuery closed"))

    async def cmd(self, text: str, timeout: float = 8.0):
        """Send one command. Returns the list of data lines. Raises QueryError on error id != 0."""
        async with self._lock:
            self._buf.clear()
            self._pending = asyncio.get_running_loop().create_future()
            self._w.write((text + "\n").encode())
            await self._w.drain()
            lines, err = await asyncio.wait_for(self._pending, timeout)
            if err.get("id") != "0":
                raise QueryError(f"{text.split(' ')[0]}: id={err.get('id')} msg={err.get('msg')}")
            return lines

    # ---- helpers ----
    async def kv(self, text):
        lines = await self.cmd(text)
        return parse_line("x " + lines[0])[1] if lines else {}

    async def say(self, cid: str, msg: str):
        # TS chat limit is about 1024 bytes per message
        for chunk in _chunks(msg, 900):
            await self.cmd(f"sendtextmessage targetmode=2 target={cid} msg={escape(chunk)}")

def _chunks(s, n):
    return [s[i:i + n] for i in range(0, len(s), n)] or [""]
```

### 8.6 `bot/spotify.py`

```python
import re, time, aiohttp

URI_RE = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?(track|album|playlist|artist)/([A-Za-z0-9]+)"
    r"|spotify:(track|album|playlist|artist):([A-Za-z0-9]+)")

def to_uri(text: str):
    m = URI_RE.search(text)
    if not m:
        return None
    kind, sid = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return f"spotify:{kind}:{sid}"

class Librespot:
    """Thin client for go-librespot's local API. Verify endpoints against your pinned version."""
    def __init__(self, base, session):
        self.base, self.s = base, session

    async def _post(self, path, json=None):
        async with self.s.post(self.base + path, json=json,
                               timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status >= 400:
                raise RuntimeError(f"{path} -> HTTP {r.status}: {await r.text()}")

    async def status(self):
        async with self.s.get(self.base + "/status", timeout=aiohttp.ClientTimeout(total=5)) as r:
            r.raise_for_status()
            return await r.json()

    async def play(self, uri):    await self._post("/player/play", {"uri": uri})
    async def resume(self):       await self._post("/player/resume")
    async def pause(self):        await self._post("/player/pause")
    async def next(self):         await self._post("/player/next")
    async def prev(self):         await self._post("/player/prev")
    async def volume(self, v):    await self._post("/player/volume", {"volume": int(v)})
    async def enqueue(self, uri): await self._post("/player/add_to_queue", {"uri": uri})

class Search:
    """Spotify Web API, client-credentials flow, search only."""
    def __init__(self, cid, secret, session):
        self.cid, self.secret, self.s = cid, secret, session
        self._tok, self._exp = None, 0

    async def _token(self):
        if self._tok and time.time() < self._exp - 30:
            return self._tok
        async with self.s.post("https://accounts.spotify.com/api/token",
                               data={"grant_type": "client_credentials"},
                               auth=aiohttp.BasicAuth(self.cid, self.secret)) as r:
            r.raise_for_status()
            d = await r.json()
        self._tok, self._exp = d["access_token"], time.time() + d["expires_in"]
        return self._tok

    async def tracks(self, query, limit=5):
        tok = await self._token()
        async with self.s.get("https://api.spotify.com/v1/search",
                              params={"q": query, "type": "track", "limit": limit},
                              headers={"Authorization": f"Bearer {tok}"}) as r:
            r.raise_for_status()
            d = await r.json()
        return [{"uri": t["uri"], "name": t["name"],
                 "artists": ", ".join(a["name"] for a in t["artists"])}
                for t in d.get("tracks", {}).get("items", [])]
```

### 8.7 `bot/commands.py`

```python
import asyncio, subprocess
from .spotify import to_uri

REGISTRY = {}   # name -> (handler, admin_only)

def command(name, *aliases, admin=False):
    def deco(fn):
        for n in (name, *aliases):
            REGISTRY[n] = (fn, admin)
        return fn
    return deco

class Ctx:
    def __init__(self, cfg, cq, lr, search, uid, nick, cid):
        self.cfg, self.cq, self.lr, self.search = cfg, cq, lr, search
        self.uid, self.nick, self.cid = uid, nick, cid

# ---------------- music ----------------
@command("play", "p")
async def play(ctx, arg):
    if not arg:
        await ctx.lr.resume(); return "Resumed."
    uri, label = to_uri(arg), arg
    if not uri:
        hits = await ctx.search.tracks(arg, limit=1)
        if not hits:
            return "Nothing found."
        uri, label = hits[0]["uri"], f'{hits[0]["name"]} - {hits[0]["artists"]}'
    await ctx.lr.play(uri)
    return f"Playing: {label}"

@command("queue", "q")
async def queue(ctx, arg):
    if not arg:
        return "Usage: queue <song name or Spotify link>"
    uri, label = to_uri(arg), arg
    if not uri:
        hits = await ctx.search.tracks(arg, limit=1)
        if not hits:
            return "Nothing found."
        uri, label = hits[0]["uri"], f'{hits[0]["name"]} - {hits[0]["artists"]}'
    await ctx.lr.enqueue(uri)
    return f"Queued: {label}"

@command("pause")
async def pause(ctx, arg):
    await ctx.lr.pause(); return "Paused."

@command("resume", "r")
async def resume(ctx, arg):
    await ctx.lr.resume(); return "Resumed."

@command("skip", "next", "s")
async def skip(ctx, arg):
    await ctx.lr.next(); return "Skipped."

@command("prev", "back")
async def prev(ctx, arg):
    await ctx.lr.prev(); return "Previous track."

@command("vol", "volume", "v")
async def vol(ctx, arg):
    try:
        v = max(0, min(int(arg), ctx.cfg.max_volume))
    except ValueError:
        return f"Usage: vol <0-{ctx.cfg.max_volume}>"
    await ctx.lr.volume(v); return f"Volume: {v}"

@command("np", "now")
async def np(ctx, arg):
    st = await ctx.lr.status()
    t = st.get("track")
    if not t:
        return "Nothing playing."
    artists = ", ".join(t.get("artist_names", []))     # field names: verify for your version
    state = "paused" if st.get("paused") else "playing"
    return f'{state}: {t.get("name", "?")} - {artists}'

@command("help", "h")
async def help_(ctx, arg):
    p = ctx.cfg.prefix
    return (f"{p}play <name|link>, {p}queue <name|link>, {p}pause, {p}resume, {p}skip, "
            f"{p}prev, {p}vol <0-{ctx.cfg.max_volume}>, {p}np | admin: {p}restart, "
            f"{p}reconnect, {p}audio, {p}status")

# ---------------- bot control (admin) ----------------
def _sh(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=20)

@command("restart", admin=True)
async def restart(ctx, arg):
    # Stops supervisord, so the container exits and Docker's restart policy brings it back.
    asyncio.get_running_loop().call_later(1.5, lambda: _sh("supervisorctl", "shutdown"))
    return "Restarting container..."

@command("reconnect", admin=True)
async def reconnect(ctx, arg):
    url = open("/tmp/ts_url").read().strip()
    _sh("/opt/ts3client/ts3client_runscript.sh", url)
    return "Reconnect requested."

@command("audio", admin=True)
async def audio(ctx, arg):
    r = _sh("supervisorctl", "restart", "go-librespot")
    return "Audio backend restarted." if r.returncode == 0 else f"Failed: {r.stdout.strip()}"

@command("status", admin=True)
async def status(ctx, arg):
    st = await ctx.lr.status()
    return f"Spotify API ok; paused={st.get('paused')}; volume={st.get('volume')}"
```

### 8.8 `bot/app.py`

```python
import asyncio, logging, time
import aiohttp
from aiohttp import web
from .config import CFG
from .clientquery import ClientQuery, QueryError
from .spotify import Librespot, Search
from .tsescape import strip_bbcode
from .commands import REGISTRY, Ctx

log = logging.getLogger("app")

class App:
    def __init__(self):
        self.session = None
        self.cq = None
        self.lr = None
        self.search = None
        self.my_clid = None
        self.my_cid = None
        self.last_cmd = {}          # uid -> timestamp (rate limit)
        self.ts_ok = False
        self.spotify_ok = False

    async def on_event(self, name, f):
        if name != "notifytextmessage" or f.get("targetmode") != "2":
            return
        if f.get("invokerid") == self.my_clid:
            return
        msg = strip_bbcode(f.get("msg", ""))
        if not msg.startswith(CFG.prefix):
            return
        cmd, _, arg = msg[len(CFG.prefix):].partition(" ")
        entry = REGISTRY.get(cmd.lower())
        if not entry:
            return
        handler, admin_only = entry
        uid, nick = f.get("invokeruid", ""), f.get("invokername", "?")
        if admin_only and uid not in CFG.admin_uids:
            await self.cq.say(self.my_cid, "Admins only.")
            return
        now = time.time()
        if now - self.last_cmd.get(uid, 0) < CFG.cooldown:
            return
        self.last_cmd[uid] = now
        ctx = Ctx(CFG, self.cq, self.lr, self.search, uid, nick, self.my_cid)
        try:
            reply = await handler(ctx, arg.strip())
        except Exception as e:
            log.exception("command failed: %s", cmd)
            reply = f"Error: {e}"
        if reply:
            await self.cq.say(self.my_cid, reply)

    async def _ts_session(self):
        """Connect to ClientQuery, register for chat events, keep the connection alive."""
        self.cq = ClientQuery(CFG.cq_host, CFG.cq_port, CFG.cq_apikey, self.on_event)
        await self.cq.connect()
        sch = (await self.cq.kv("currentschandlerid")).get("schandlerid", "1")
        await self.cq.cmd(f"clientnotifyregister schandlerid={sch} event=notifytextmessage")
        while self.cq.connected:
            try:
                who = await self.cq.kv("whoami")      # fails if not connected to a server
                self.my_clid, self.my_cid = who.get("clid"), who.get("cid")
                self.ts_ok = bool(self.my_clid)
            except (QueryError, asyncio.TimeoutError):
                self.ts_ok = False
            await asyncio.sleep(10)

    async def ts_loop(self):
        delay = 2
        while True:
            try:
                await self._ts_session()
            except Exception as e:
                log.warning("ClientQuery session ended: %s", e)
            self.ts_ok = False
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def spotify_loop(self):
        while True:
            try:
                await self.lr.status()
                self.spotify_ok = True
            except Exception:
                self.spotify_ok = False
            await asyncio.sleep(15)

    async def health(self, request):
        ok = self.ts_ok and self.spotify_ok
        return web.json_response({"ts": self.ts_ok, "spotify": self.spotify_ok},
                                 status=200 if ok else 503)

    async def run(self):
        self.session = aiohttp.ClientSession()
        self.lr = Librespot(CFG.lr_url, self.session)
        self.search = Search(CFG.sp_client_id, CFG.sp_client_secret, self.session)

        app = web.Application()
        app.router.add_get("/health", self.health)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", CFG.health_port).start()

        # best-effort: set initial volume once go-librespot is up
        asyncio.create_task(self._init_volume())
        await asyncio.gather(self.ts_loop(), self.spotify_loop())

    async def _init_volume(self):
        for _ in range(30):
            try:
                await self.lr.volume(CFG.initial_volume); return
            except Exception:
                await asyncio.sleep(2)
```

### 8.9 `bot/__main__.py`

```python
import asyncio, logging
from .app import App

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
asyncio.run(App().run())
```

Also create an empty `bot/__init__.py`.

### 8.10 Command reference

| Command | Who | Does |
|---|---|---|
| `!play <name\|link>` | everyone | Search and play, or play a Spotify link or URI. With no argument, resume. |
| `!queue <name\|link>` | everyone | Add a track to the queue |
| `!pause` / `!resume` | everyone | Pause or resume |
| `!skip` / `!prev` | everyone | Next or previous track |
| `!vol <0-N>` | everyone | Set volume, clamped to `MAX_VOLUME` |
| `!np` | everyone | Now playing |
| `!help` | everyone | Command list |
| `!restart` | admin | Restart the whole container (supervisord shuts down, Docker restarts it) |
| `!reconnect` | admin | Re-issue the `ts3server://` connect URL |
| `!audio` | admin | Restart go-librespot only |
| `!status` | admin | Spotify and bot health |

Optional later additions: per-role permissions (a DJ list), vote-skip, `!shuffle`, `!repeat`, and `!seek`.

---

## 9. First-time setup, per bot

Do one bot at a time, and stop its normal container first (the same volume and Spotify account can't run twice).

**Step 1: build the image**
```bash
docker compose build
# First build prints the TS client sha256. Copy it into TS3_SHA256 in the Dockerfile and rebuild.
```

**Step 2: start the bot in setup mode**
```bash
mkdir -p data/bot1
docker compose run --rm --service-ports --name tsbot1-setup \
  -e SETUP_MODE=1 -e VNC_PASSWORD=choose-something \
  -p 127.0.0.1:8888:8889 -p 127.0.0.1:5900:5900 \
  bot1
```
On a remote VPS, tunnel from your laptop: `ssh -L 8888:127.0.0.1:8888 -L 5900:127.0.0.1:5900 user@vps`.

**Step 3: link Spotify**
1. In the logs, go-librespot prints a Spotify login URL.
2. Open it in your browser, log in with **this bot's Premium account**, and approve. The browser is redirected to `http://127.0.0.1:8888/...`, which the tunnel and socat forward into the container.
3. Credentials are saved under `data/bot1/librespot/`, so this is a one-time step.

**Step 4: configure the TeamSpeak client over VNC**
Connect a VNC viewer to `127.0.0.1:5900`, then:
1. Accept the license.
2. **Settings > Plugins:** enable **ClientQuery**, open its settings, and **copy the API key** into `bots/bot1.env` as `TS_CLIENTQUERY_APIKEY`.
3. **Settings > Capture:** mode PulseAudio, device **Default** (this is `music.monitor`). Choose **Continuous Transmission** (not push-to-talk or voice activation). Turn **off** echo reduction, automatic gain, and noise suppression.
4. **Settings > Playback:** PulseAudio, device Default (the void sink).
5. **Settings > Capture > Voice encoder:** pick the highest music-oriented quality if offered.
6. **Identity:** note the unique ID (needed for admins and the server's permission setup). If the server demands a higher security level, upgrade it here.
7. Make sure the client is connected to the channel, then close VNC. Settings persist in `data/bot1/home/.ts3client`.

**Step 5: run normally**
```bash
# Ctrl+C the setup container, then:
docker compose up -d bot1
docker compose logs -f bot1
```
Repeat steps 2 to 5 for each bot.

**Alternative for pairing on the same LAN:** go-librespot also supports zeroconf, where the bot appears in the Spotify app's device list like a speaker. That needs mDNS to reach the container, which does not work across the internet to a VPS or inside Docker Desktop on a Mac, so OAuth interactive login is the reliable path.

---

## 10. Running several bots

- Each bot = its own service, `bots/botN.env`, `data/botN` volume, **its own Spotify Premium account**, and its own TeamSpeak identity (do the VNC step per bot; don't copy one bot's `.ts3client` to another, or they'll share a UID).
- Give each a distinct `TS_NICK` and `SPOTIFY_DEVICE_NAME`.
- Sizing: about 0.5 to 1 vCPU and 600 MB to 1 GB RAM each. Ten bots needs a beefy VPS (roughly 8 to 12 GB).
- Disk is tiny (no caching). The per-bot volume holds only settings and credentials.

---

## 11. Operations

| Task | Command |
|---|---|
| Logs | `docker compose logs -f bot1` |
| Health | `docker inspect --format '{{.State.Health.Status}}' tsbot1` |
| Restart one bot | `docker compose restart bot1` (or `!restart` in chat) |
| Shell in | `docker compose exec bot1 bash` |
| Process status | `docker compose exec bot1 supervisorctl status` |
| Update | `docker compose build --pull && docker compose up -d` |
| Backup | Copy `data/` (Spotify credentials and TS settings and identities). Treat it as secret. |

Healthcheck logic: `/health` returns 200 only if the ClientQuery session is up and connected to a TS server, **and** go-librespot's API answers. Autoheal restarts a container after 3 consecutive failures.

Version bumps: pin go-librespot and the TS client in the Dockerfile, test a new version on **one** bot first, then roll out.

---

## 12. Test checklist

1. `docker compose logs bot1` shows go-librespot started, the TS client launched, and the controller connected to ClientQuery.
2. The bot appears in your TS channel.
3. `!help` gets a reply in channel chat.
4. `!play <song>` produces audio you can hear in the channel.
5. `!pause`, `!resume`, `!skip`, `!vol 20`, and `!np` all work.
6. `!play <spotify link>` works (a pasted link arrives as BBCode, which the controller strips).
7. A non-admin sending `!restart` gets "Admins only."
8. An admin `!restart` brings the container back and the bot rejoins on its own.
9. Kill the TS server connection (or firewall it for a minute), and the bot reconnects.
10. Run two bots at once, playing different songs, and confirm no interference.
11. Leave it playing for 24 hours and watch the health status.

---

## 13. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| No audio in channel | TS capture device isn't `Default` / `music.monitor`; push-to-talk is on; channel talk power too low; go-librespot not outputting to sink `music`. Check with `pactl list sources short` and `pactl list sink-inputs` inside the container. |
| Audio sounds terrible | Channel codec not Opus Music, or voice processing (AGC, noise suppression) still on. |
| Controller can't authenticate | Wrong API key, or the ClientQuery plugin isn't enabled. Redo setup step 4.2. |
| `!play` says "Nothing found" or errors | Search app credentials wrong, or Spotify restricted the endpoint. Test the client-credentials token manually. Pasting links still works as a fallback. |
| Play command errors | go-librespot endpoint or field differs in your pinned version. Compare to its API docs. |
| Bot can't join / "insufficient permissions" | Server group lacks join or talk permissions, or the identity security level is too low. Talk to the server admin. |
| Spotify login stops working later | Token or credentials invalidated (subscription lapsed, password change, Spotify change). Delete `data/botN/librespot/` state and redo setup step 3. Also update go-librespot. |
| TS client crashes at start | Missing libraries: run `ldd` on the binary and add packages. |
| Bot replies are slow or dropped | Anti-flood. Ask for `b_client_ignore_antiflood`. |
| Two bots interrupt each other | They share a Spotify account. Use one account per bot. |

---

## 14. Verify before you trust it

I wrote this from memory of how these tools work, without running it. Check these first:

1. **go-librespot:** exact config option names (`audio_backend`, `audio_device`, `credentials.interactive.callback_port`, `server.*`), the `--config_dir` flag, API endpoints and JSON fields (`/player/play`, `/player/volume`, `/status`, `track.artist_names`), the release asset name, and where credentials persist.
2. **TeamSpeak client:** current 3.6.x download URL, whether `./installer.run --noexec --target <dir>` works for that file, that `ts3client_runscript.sh` accepts a `ts3server://` URL, that the ClientQuery plugin is present and its API key is available in the Settings UI, and compatibility with your server (especially TeamSpeak 6).
3. **ClientQuery details:** whether `sendtextmessage targetmode=2 target=<cid>` is the exact accepted form, whether `currentschandlerid` and `whoami` return the fields I used, and the banner and line-ending behavior (the parser may need tweaks).
4. **Spotify Web API:** whether client-credentials search still works for new developer apps under current rules, and any dashboard requirements. If not, fall back to link-only `!play`, or add a third-party search.
5. **Dockerfile packages:** the TS client's required libraries (use `ldd`).
6. **Spotify ToS and account risk:** decide whether you accept it.

---

## 15. Reusing your old repo

Before writing code from scratch, recover the working commit from `mohammed-Araf/TS-Music-Bot` (`git log --all --graph`, check the parents of the bad merge). If the old bot used librespot or Spotify Connect, its TeamSpeak chat handling and command logic may be reusable inside the `controller/` module. If it used the Spotify Web API directly for playback, replace that part with the go-librespot calls above.

---

## 16. Build order

1. Get the container running with only Xvfb, PulseAudio, and the TS client, and hear a test tone from `music.monitor` in the channel (`paplay` to sink `music`).
2. Add go-librespot, pair it, and hear Spotify through the channel by selecting the device manually.
3. Add the controller with `!play`, `!pause`, `!vol`, and test chat commands.
4. Add the remaining commands, permissions, rate limit, and admin commands.
5. Add the healthcheck, autoheal, and logging polish.
6. Create the second bot and test concurrency.
7. Tag `v1-working` in git.
