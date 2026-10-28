# syntax=docker/dockerfile:1.7
FROM --platform=linux/amd64 debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

# ---- pinned versions ----
ARG TS3_VERSION=3.6.2
ARG TS3_SHA256=59f110438971a23f904a700e7dd0a811cf99d4e6b975ba3aa45962d43b006422
ARG GOLIBRESPOT_VERSION=v0.10.5
ARG GOLIBRESPOT_ASSET=go-librespot_linux_x86_64.tar.gz

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl bzip2 xz-utils sqlite3 procps socat gettext-base \
      supervisor xvfb x11vnc \
      pulseaudio pulseaudio-utils libpulse0 libasound2 libasound2-plugins \
      libogg0 libvorbis0a libvorbisfile3 libflac12 \
      python3 python3-venv python3-pip \
      fonts-dejavu-core \
      libevent-2.1-7 libpci3 libxslt1.1 libatomic1 \
      libglib2.0-0 libnss3 libfontconfig1 libdbus-1-3 libegl1 libgl1 \
      libx11-xcb1 libxrender1 libxext6 libxi6 libxtst6 libxrandr2 libxss1 \
      libxcomposite1 libxcursor1 libxdamage1 libxkbcommon-x11-0 \
      libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
      libxcb-render-util0 libxcb-xkb1 libxcb-shape0 libxcb-randr0 \
      libxcb-xfixes0 libxcb-sync1 libxcb-shm0 libxcb-glx0 \
 && rm -rf /var/lib/apt/lists/*

# ---- TeamSpeak 3 client ----
RUN curl -fsSL -o /tmp/ts3.run \
      "https://files.teamspeak-services.com/releases/client/${TS3_VERSION}/TeamSpeak3-Client-linux_amd64-${TS3_VERSION}.run" \
 && sha256sum /tmp/ts3.run \
 && ( [ -z "${TS3_SHA256}" ] || echo "${TS3_SHA256}  /tmp/ts3.run" | sha256sum -c - ) \
 && chmod +x /tmp/ts3.run \
 && printf "q\ny\n" | /tmp/ts3.run --noexec --target /opt/ts3client \
 && chmod -R a+rX /opt/ts3client \
 && rm /tmp/ts3.run

# Pre-bundle ClientQuery plugin
COPY docker/ts3_plugins/plugins/ /opt/ts3client/plugins/
RUN chmod -R a+rX /opt/ts3client/plugins

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
COPY docker/asound.conf /etc/asound.conf
COPY docker/ /opt/bot/docker/
COPY controller/ /opt/bot/controller/
RUN chmod +x /opt/bot/docker/*.sh \
 && chown -R bot:bot /opt/bot \
 && python3 -m venv /opt/bot/venv \
 && /opt/bot/venv/bin/pip install --no-cache-dir -r /opt/bot/controller/requirements.txt

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fs http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/opt/bot/docker/entrypoint.sh"]
