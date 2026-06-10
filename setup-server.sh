#!/bin/bash
set -e

echo "=== Updating packages ==="
sudo apt-get update

echo "=== Installing dependencies ==="
sudo apt-get install -y xvfb tmux pulseaudio pulseaudio-utils openjdk-17-jre-headless openjfx dbus-x11 mpv netcat-openbsd git wget curl unzip libglib2.0-0 libx11-6 libxrender1 libdbus-1-3 libnss3 libegl1 libfontconfig1 libxi6 libxrandr2 libxtst6 libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 dbus-user-session libssl-dev libasound2-dev libdbus-1-dev

echo "=== Installing yt-dlp ==="
sudo wget https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/dlp/yt-dlp || sudo chmod a+rx /usr/local/bin/yt-dlp
sudo ln -sf /usr/local/bin/yt-dlp /usr/local/bin/youtube-dl

echo "=== Installing TeamSpeak 3 Client 3.6.2 ==="
if [ ! -d "/opt/teamspeak3" ]; then
  wget https://files.teamspeak-services.com/releases/client/3.6.2/TeamSpeak3-Client-linux_amd64-3.6.2.run
  chmod +x TeamSpeak3-Client-linux_amd64-3.6.2.run
  # Automate license acceptance: press q then y
  (echo "q"; echo "y") | ./TeamSpeak3-Client-linux_amd64-3.6.2.run
  sudo mv TeamSpeak3-Client-linux_amd64 /opt/teamspeak3
  sudo ln -sf /opt/teamspeak3/ts3client_runscript.sh /usr/local/bin/teamspeak3
  rm TeamSpeak3-Client-linux_amd64-3.6.2.run
else
  echo "TeamSpeak 3 already installed."
fi

echo "=== Installing ncspot ==="
if [ ! -f "/usr/local/bin/ncspot" ]; then
  LATEST_TAG=$(curl -sSL -o /dev/null -w "%{url_effective}" https://github.com/hrkfdn/ncspot/releases/latest | grep -oE "[^/]+$")
  wget "https://github.com/hrkfdn/ncspot/releases/download/${LATEST_TAG}/ncspot-${LATEST_TAG}-linux-x86_64.tar.gz"
  tar -xzf "ncspot-${LATEST_TAG}-linux-x86_64.tar.gz"
  sudo mv ncspot /usr/local/bin/ncspot
  sudo chmod +x /usr/local/bin/ncspot
  rm "ncspot-${LATEST_TAG}-linux-x86_64.tar.gz"
else
  echo "ncspot already installed."
fi

echo "=== Installing spotify_player ==="
if [ ! -f "/usr/local/bin/spotify_player" ]; then
  LATEST_SP_TAG=$(curl -sSL -o /dev/null -w "%{url_effective}" https://github.com/aome510/spotify-player/releases/latest | grep -oE "[^/]+$")
  wget "https://github.com/aome510/spotify-player/releases/download/${LATEST_SP_TAG}/spotify_player-x86_64-unknown-linux-gnu.tar.gz"
  tar -xzf "spotify_player-x86_64-unknown-linux-gnu.tar.gz"
  sudo mv spotify_player /usr/local/bin/spotify_player
  sudo chmod +x /usr/local/bin/spotify_player
  rm "spotify_player-x86_64-unknown-linux-gnu.tar.gz"
else
  echo "spotify_player already installed."
fi

echo "=== Setup complete ==="
