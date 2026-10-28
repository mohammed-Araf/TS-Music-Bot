#!/usr/bin/env bash
# ==============================================================================
#      🎵 TeamSpeak 3 Spotify Music Bot - 1-Click All-in-One Installer 🎵
# ==============================================================================
# You can edit the configuration settings below directly in this file, OR you
# can leave them as-is and the script will interactively prompt you for them.
# ==============================================================================

# ⚙️ CONFIGURATION SETTINGS (Edit here directly if you prefer!)
TS_HOST="ts.example.com"                  # TeamSpeak Server Address (IP or domain)
TS_PORT="9987"                            # TeamSpeak Server Port (default: 9987)
TS_CHANNEL="Music"                        # Target Music Channel Name
TS_CHANNEL_PASSWORD=""                    # Channel Password (leave empty if none)
TS_SERVER_PASSWORD=""                     # Server Password (leave empty if none)
TS_NICK="☠ ʀᴀɢᴇ ʙᴏᴛ ☠"                       # Bot Nickname in TeamSpeak
ADMIN_SERVER_GROUPS="6"                   # Server Group ID for Bot Admins (6 = Server Admin)
ALLOWED_SERVER_GROUPS="50"                # Server Group ID allowed to play music (blank for everyone)

# ==============================================================================
# DO NOT EDIT BELOW THIS LINE UNLESS YOU KNOW WHAT YOU ARE DOING
# ==============================================================================

set -euo pipefail

# Terminal colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "=========================================================="
echo "      🎵 TeamSpeak 3 Spotify Music Bot Installer 🎵       "
echo "=========================================================="
echo -e "${NC}"

# Check for non-interactive flag (-y or --yes)
AUTO_CONFIRM=false
for arg in "$@"; do
    if [ "$arg" = "-y" ] || [ "$arg" = "--yes" ]; then
        AUTO_CONFIRM=true
    fi
done

# 1. Check if repository files are present, or clone if missing
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${YELLOW}▶ Project files not found in current folder.${NC}"
    echo -e "${CYAN}▶ Downloading latest TS-Music-Bot repository...${NC}"
    if ! command -v git >/dev/null 2>&1; then
        if [ "$(uname)" = "Linux" ] && command -v apt-get >/dev/null 2>&1; then
            echo -e "${CYAN}Installing git...${NC}"
            sudo apt-get update -qq && sudo apt-get install -y -qq git
        fi
    fi
    git clone https://github.com/mohammed-Araf/TS-Music-Bot.git
    cd TS-Music-Bot
    echo -e "${GREEN}✅ Downloaded repository to $(pwd)${NC}\n"
fi

# 2. Check & Install Docker
echo -e "${BLUE}▶ [1/4] Checking Docker installation...${NC}"
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${YELLOW}Docker is not installed.${NC}"
    if [ "$(uname)" = "Linux" ]; then
        echo -e "${CYAN}Installing Docker automatically via official script (https://get.docker.com)...${NC}"
        curl -fsSL https://get.docker.com | sh
        sudo systemctl start docker || true
        sudo systemctl enable docker || true
        sudo usermod -aG docker "$USER" || true
        echo -e "${GREEN}✅ Docker installed successfully!${NC}"
    elif [ "$(uname)" = "Darwin" ]; then
        echo -e "${RED}Docker Desktop is required on macOS.${NC}"
        echo -e "Please download it from: ${BOLD}https://www.docker.com/products/docker-desktop/${NC}"
        echo "Start Docker Desktop, then run this script again."
        exit 1
    else
        echo -e "${RED}Please install Docker from: https://www.docker.com/products/docker-desktop/${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Docker is already installed.${NC}"
fi

# Determine compose command
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    if [ "$(uname)" = "Linux" ] && command -v apt-get >/dev/null 2>&1; then
        echo -e "${CYAN}Installing Docker Compose plugin...${NC}"
        sudo apt-get update -qq && sudo apt-get install -y -qq docker-compose-plugin
        DOCKER_COMPOSE="docker compose"
    else
        echo -e "${RED}Docker Compose not found. Please install Docker Compose v2.${NC}"
        exit 1
    fi
fi

# Check if docker commands require sudo
if ! docker info >/dev/null 2>&1; then
    if sudo docker info >/dev/null 2>&1; then
        DOCKER_COMPOSE="sudo $DOCKER_COMPOSE"
    fi
fi
echo -e "${GREEN}✅ Docker Compose is ready (${DOCKER_COMPOSE}).${NC}\n"

# 3. Read Existing Config if Present
if [ -f .env.common ]; then
    FILE_HOST=$(grep '^TS_HOST=' .env.common | cut -d '=' -f2- || true)
    FILE_PORT=$(grep '^TS_PORT=' .env.common | cut -d '=' -f2- || true)
    FILE_CHAN=$(grep '^TS_CHANNEL=' .env.common | cut -d '=' -f2- || true)
    FILE_CPW=$(grep '^TS_CHANNEL_PASSWORD=' .env.common | cut -d '=' -f2- || true)
    FILE_SPW=$(grep '^TS_SERVER_PASSWORD=' .env.common | cut -d '=' -f2- || true)

    [ -n "$FILE_HOST" ] && [ "$TS_HOST" = "ts.example.com" ] && TS_HOST="$FILE_HOST"
    [ -n "$FILE_PORT" ] && [ "$TS_PORT" = "9987" ] && TS_PORT="$FILE_PORT"
    [ -n "$FILE_CHAN" ] && [ "$TS_CHANNEL" = "Music" ] && TS_CHANNEL="$FILE_CHAN"
    [ -n "$FILE_CPW" ] && [ -z "$TS_CHANNEL_PASSWORD" ] && TS_CHANNEL_PASSWORD="$FILE_CPW"
    [ -n "$FILE_SPW" ] && [ -z "$TS_SERVER_PASSWORD" ] && TS_SERVER_PASSWORD="$FILE_SPW"
fi
if [ -f bots/bot1.env ]; then
    FILE_NICK=$(grep '^TS_NICK=' bots/bot1.env | cut -d '=' -f2- || true)
    FILE_ADM=$(grep '^ADMIN_SERVER_GROUPS=' bots/bot1.env | cut -d '=' -f2- || true)
    FILE_ALL=$(grep '^ALLOWED_SERVER_GROUPS=' bots/bot1.env | cut -d '=' -f2- || true)

    [ -n "$FILE_NICK" ] && [ "$TS_NICK" = "MusicBot1" ] && TS_NICK="$FILE_NICK"
    [ -n "$FILE_ADM" ] && [ "$ADMIN_SERVER_GROUPS" = "6" ] && ADMIN_SERVER_GROUPS="$FILE_ADM"
    [ -n "$FILE_ALL" ] && [ "$ALLOWED_SERVER_GROUPS" = "50" ] && ALLOWED_SERVER_GROUPS="$FILE_ALL"
fi

# 4. Interactive Configuration Prompts (if running in terminal and not auto-confirmed)
echo -e "${BLUE}▶ [2/4] Configuring Bot Credentials...${NC}"

if [ "$AUTO_CONFIRM" = false ] && [ -t 0 ]; then
    echo -e "${CYAN}Press Enter to accept the value shown in [brackets]:${NC}"

    read -rp "$(echo -e "${BOLD}TeamSpeak Server Address (IP or Domain)${NC} [${TS_HOST}]: ")" INP_HOST
    TS_HOST="${INP_HOST:-$TS_HOST}"

    read -rp "$(echo -e "${BOLD}TeamSpeak Server Port${NC} [${TS_PORT}]: ")" INP_PORT
    TS_PORT="${INP_PORT:-$TS_PORT}"

    read -rp "$(echo -e "${BOLD}Target Channel Name${NC} [${TS_CHANNEL}]: ")" INP_CHAN
    TS_CHANNEL="${INP_CHAN:-$TS_CHANNEL}"

    read -rp "$(echo -e "${BOLD}Channel Password${NC} (leave blank if none) [${TS_CHANNEL_PASSWORD}]: ")" INP_CPW
    TS_CHANNEL_PASSWORD="${INP_CPW:-$TS_CHANNEL_PASSWORD}"

    read -rp "$(echo -e "${BOLD}Server Password${NC} (leave blank if none) [${TS_SERVER_PASSWORD}]: ")" INP_SPW
    TS_SERVER_PASSWORD="${INP_SPW:-$TS_SERVER_PASSWORD}"

    read -rp "$(echo -e "${BOLD}Bot Nickname${NC} [${TS_NICK}]: ")" INP_NICK
    TS_NICK="${INP_NICK:-$TS_NICK}"

    read -rp "$(echo -e "${BOLD}Admin Server Group ID${NC} (e.g. 6 for Server Admin) [${ADMIN_SERVER_GROUPS}]: ")" INP_ADM
    ADMIN_SERVER_GROUPS="${INP_ADM:-$ADMIN_SERVER_GROUPS}"

    read -rp "$(echo -e "${BOLD}Music Playback Role ID${NC} (e.g. 50, or leave blank for everyone) [${ALLOWED_SERVER_GROUPS}]: ")" INP_ALL
    ALLOWED_SERVER_GROUPS="${INP_ALL:-$ALLOWED_SERVER_GROUPS}"
else
    echo -e "${GREEN}Using configured settings for ${BOLD}${TS_NICK}${NC} -> ${BOLD}${TS_HOST}:${TS_PORT}${NC}"
fi

# 5. Overwrite/Write Configuration Files
echo -e "\n${BLUE}▶ [3/4] Writing configuration files...${NC}"

# Preserve existing Spotify API keys if set in .env.common
EXISTING_SPOTIFY_ID=""
EXISTING_SPOTIFY_SECRET=""
if [ -f .env.common ]; then
    EXISTING_SPOTIFY_ID=$(grep '^SPOTIFY_CLIENT_ID=' .env.common | cut -d '=' -f2- || true)
    EXISTING_SPOTIFY_SECRET=$(grep '^SPOTIFY_CLIENT_SECRET=' .env.common | cut -d '=' -f2- || true)
fi

cat > .env.common <<EOF
# TeamSpeak 3 Server Configuration
TS_HOST=${TS_HOST}
TS_PORT=${TS_PORT}
TS_CHANNEL=${TS_CHANNEL}
TS_SERVER_PASSWORD=${TS_SERVER_PASSWORD}
TS_CHANNEL_PASSWORD=${TS_CHANNEL_PASSWORD}

# Bot Playback Settings
CMD_PREFIX=!
CMD_COOLDOWN=1.5
MAX_VOLUME=80
INITIAL_VOLUME=40

# Spotify Search API Keys (Optional - use !spotifykeys in chat to configure)
SPOTIFY_CLIENT_ID=${EXISTING_SPOTIFY_ID}
SPOTIFY_CLIENT_SECRET=${EXISTING_SPOTIFY_SECRET}
EOF

mkdir -p bots
cat > bots/bot1.env <<EOF
# Bot Identity & Roles
TS_NICK=${TS_NICK}
SPOTIFY_DEVICE_NAME=${TS_NICK}
ADMIN_SERVER_GROUPS=${ADMIN_SERVER_GROUPS}
ALLOWED_SERVER_GROUPS=${ALLOWED_SERVER_GROUPS}
ADMIN_UIDS=
EOF

mkdir -p data/bot1
echo -e "${GREEN}✅ Saved settings to .env.common and bots/bot1.env!${NC}\n"

# 6. Launch Container
echo -e "${BLUE}▶ [4/4] Starting bot container via Docker...${NC}"
${DOCKER_COMPOSE} up -d bot1

echo -e "\n${GREEN}${BOLD}=========================================================="
echo "   🎉 SUCCESS! TeamSpeak Music Bot is UP and RUNNING!   "
echo "==========================================================${NC}"
echo -e "${CYAN}Next Steps:${NC}"
echo -e "1. Open TeamSpeak and join channel: ${BOLD}${TS_CHANNEL}${NC}"
echo -e "2. In the channel chat, type: ${BOLD}!login${NC}"
echo -e "3. Open the link on your phone/browser to link your Spotify Premium account."
echo -e "4. Type ${BOLD}!play <song name>${NC} and enjoy the music!"
echo ""
echo -e "${YELLOW}Helpful Management Commands:${NC}"
echo -e "• View live logs:  ${BOLD}${DOCKER_COMPOSE} logs -f bot1${NC}"
echo -e "• Stop the bot:    ${BOLD}${DOCKER_COMPOSE} down${NC}"
echo -e "• Start the bot:   ${BOLD}${DOCKER_COMPOSE} up -d bot1${NC}"
echo -e "• Reconfigure:     ${BOLD}bash install.sh${NC}"
echo ""
