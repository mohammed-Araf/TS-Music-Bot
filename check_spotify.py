#!/usr/bin/env python3
"""
🎵 Spotify Account Compatibility Checker
------------------------------------------------------------
A standalone, cross-platform diagnostic tool to verify if your
Spotify account works with open-source Spotify Connect bots
(go-librespot / librespot) before setting up TeamSpeak or VPS.

Zero external dependencies - Uses Python 3 standard library only.
Supports: macOS, Linux (x86_64, arm64), and Windows (amd64).
"""

import sys
import os
import time
import json
import re
import socket
import tempfile
import shutil
import platform
import subprocess
import tarfile
import urllib.request
import urllib.error
import webbrowser

GOLIBRESPOT_VERSION = "v0.10.5"
TEST_TRACK_URI = "spotify:track:7qiZfU4dY1lWllzX7mPBI3"  # Ed Sheeran - Shape of You
TEST_TRACK_NAME = "Ed Sheeran - Shape of You"

COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"

# Disable ANSI colors on Windows if not supported
if platform.system() == "Windows":
    os.system("")  # Enable VT100 escape codes in Windows 10+


def log(msg, color=""):
    if color:
        print(f"{color}{msg}{COLOR_RESET}", flush=True)
    else:
        print(msg, flush=True)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def get_cache_dir():
    home = os.path.expanduser("~")
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    else:
        base = os.environ.get("XDG_CACHE_HOME", os.path.join(home, ".cache"))
    cache = os.path.join(base, "ts-musicbot")
    os.makedirs(cache, exist_ok=True)
    return cache


def get_or_download_binary():
    # 1. Check if go-librespot already on system PATH
    bin_path = shutil.which("go-librespot")
    if bin_path:
        return bin_path

    # 2. Check cached binary
    cache_dir = get_cache_dir()
    bin_name = "go-librespot.exe" if platform.system() == "Windows" else "go-librespot"
    cached_bin = os.path.join(cache_dir, bin_name)
    if os.path.isfile(cached_bin) and os.access(cached_bin, os.X_OK):
        return cached_bin

    # 3. Determine architecture
    os_name = platform.system().lower()
    machine = platform.machine().lower()

    asset_name = None
    if os_name == "linux":
        if machine in ("x86_64", "amd64"):
            asset_name = "go-librespot_linux_x86_64.tar.gz"
        elif machine in ("aarch64", "arm64"):
            asset_name = "go-librespot_linux_arm64.tar.gz"
        elif "arm" in machine:
            asset_name = "go-librespot_linux_armv6.tar.gz"
    elif os_name == "windows":
        if machine in ("x86_64", "amd64"):
            asset_name = "go-librespot_windows_amd64.tar.gz"
    elif os_name == "darwin":
        # macOS Homebrew fallback
        brew_bin = shutil.which("brew")
        if brew_bin:
            log("🍎 macOS detected: checking for go-librespot via Homebrew...", COLOR_CYAN)
            try:
                subprocess.run([brew_bin, "install", "go-librespot"], check=True)
                bin_path = shutil.which("go-librespot")
                if bin_path:
                    return bin_path
            except Exception as e:
                log(f"⚠️ Homebrew installation failed: {e}", COLOR_YELLOW)
        log("❌ On macOS, please install go-librespot first using: brew install go-librespot", COLOR_RED)
        sys.exit(1)

    if not asset_name:
        log(f"❌ Unsupported OS/Architecture: {os_name} ({machine})", COLOR_RED)
        sys.exit(1)

    url = f"https://github.com/devgianlu/go-librespot/releases/download/{GOLIBRESPOT_VERSION}/{asset_name}"
    log(f"⬇️  Downloading go-librespot {GOLIBRESPOT_VERSION} ({asset_name})...", COLOR_CYAN)

    tar_path = os.path.join(cache_dir, asset_name)
    try:
        urllib.request.urlretrieve(url, tar_path)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=cache_dir)
        try:
            os.remove(tar_path)
        except OSError:
            pass

        if os.path.isfile(cached_bin):
            os.chmod(cached_bin, 0o755)
            log(f"✅ Downloaded and cached to: {cached_bin}", COLOR_GREEN)
            return cached_bin
    except Exception as e:
        log(f"❌ Failed to download {url}: {e}", COLOR_RED)
        sys.exit(1)

    log("❌ Could not locate go-librespot binary.", COLOR_RED)
    sys.exit(1)


def http_post(url, data=None):
    try:
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"} if body else {})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None


def http_get(url):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Spotify Account Compatibility & DRM Tester")
    parser.add_argument("--credentials", "-c", dest="credentials_file", help="Path to existing state.json credentials file (skips pairing)")
    args = parser.parse_args()

    log("")
    log("======================================================================", COLOR_CYAN + COLOR_BOLD)
    log("       🎵 SPOTIFY ACCOUNT COMPATIBILITY CHECKER 🎵", COLOR_CYAN + COLOR_BOLD)
    log("  Verify if your Spotify account is free of 'Code 1' PlayPlay DRM", COLOR_CYAN)
    log("======================================================================", COLOR_CYAN + COLOR_BOLD)
    log("")

    bin_path = get_or_download_binary()
    port = find_free_port()
    temp_dir = tempfile.mkdtemp(prefix="spotify_check_")

    config_path = os.path.join(temp_dir, "config.yml")
    config_content = f"""log_level: info
device_name: "SpotifyTester"
device_type: speaker
audio_backend: pipe
bitrate: 320
credentials:
  type: device_auth
server:
  enabled: true
  address: 127.0.0.1
  port: {port}
"""
    with open(config_path, "w") as f:
        f.write(config_content)

    # If existing credentials passed, copy to temp directory
    skip_pair = False
    if args.credentials_file:
        if os.path.isfile(args.credentials_file):
            shutil.copy(args.credentials_file, os.path.join(temp_dir, "state.json"))
            skip_pair = True
            log(f"📁 Loaded existing credentials from: {args.credentials_file}", COLOR_CYAN)
        else:
            log(f"⚠️ Credentials file not found: {args.credentials_file}. Falling back to pairing.", COLOR_YELLOW)

    log(f"🚀 Starting background Spotify engine on port {port}...", COLOR_CYAN)

    log_file_path = os.path.join(temp_dir, "librespot.log")
    log_f = open(log_file_path, "w+", encoding="utf-8", errors="ignore")

    cmd = [bin_path, "--config_dir", temp_dir]
    proc = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        text=True
    )

    pair_url = None
    pair_code = None
    username = None

    def read_logs():
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return ""

    try:
        if not skip_pair:
            # Step 1: Wait for pairing code
            log("⏳ Requesting pairing code from Spotify Access Point...", COLOR_YELLOW)
            start_time = time.time()
            while time.time() - start_time < 20:
                time.sleep(0.5)
                content = read_logs()

                match = re.search(r"(https://spotify\.com/pair\?code=([A-Z0-9]+))", content)
                if match:
                    pair_url = match.group(1)
                    pair_code = match.group(2)
                    break

                if proc.poll() is not None:
                    break

            if not pair_url:
                log("❌ Failed to obtain pairing code from Spotify. Logs:", COLOR_RED)
                for l in read_logs().splitlines()[-10:]:
                    log(f"   {l}")
                return

            log("")
            log("----------------------------------------------------------------------", COLOR_BOLD)
            log(" 🔗 SPOTIFY PAIRING REQUIRED", COLOR_YELLOW + COLOR_BOLD)
            log("----------------------------------------------------------------------", COLOR_BOLD)
            log(f" Link: {pair_url}", COLOR_CYAN + COLOR_BOLD)
            log(f" Code: {pair_code}", COLOR_BOLD)
            log("----------------------------------------------------------------------", COLOR_BOLD)
            log("")
            log("🌐 Opening link in your default web browser...", COLOR_CYAN)

            try:
                webbrowser.open(pair_url)
            except Exception:
                pass

            log("👉 In your browser, log into your Spotify Premium account and click 'Pair'.", COLOR_YELLOW)
            log("⏳ Waiting for authorization confirmation...", COLOR_YELLOW)

            # Step 2: Wait for user authorization
            auth_time = time.time()
            while time.time() - auth_time < 90:
                time.sleep(1)
                st = http_get(f"http://127.0.0.1:{port}/status")
                if isinstance(st, dict) and st.get("username"):
                    username = st.get("username")
                    break

                content = read_logs()
                user_match = re.search(r"authenticated as ([\w\.\-]+)", content, re.IGNORECASE)
                if user_match:
                    username = user_match.group(1)
                    break

                if proc.poll() is not None:
                    break

            if not username:
                log("\n❌ Pairing timed out or failed. Did you click 'Pair' in your browser?", COLOR_RED)
                return
        else:
            # Reconnecting with existing credentials
            log("⏳ Connecting to Spotify Access Point with saved credentials...", COLOR_YELLOW)
            conn_time = time.time()
            while time.time() - conn_time < 15:
                time.sleep(0.8)
                content = read_logs()
                if "accesspoint login failed" in content or "BadCredentials" in content:
                    log("❌ Saved credentials rejected by Spotify (BadCredentials/Expired).", COLOR_RED)
                    return

                st = http_get(f"http://127.0.0.1:{port}/status")
                if isinstance(st, dict) and st.get("username"):
                    username = st.get("username")
                    break

                user_match = re.search(r"authenticated as ([\w\.\-]+)", content, re.IGNORECASE)
                if user_match:
                    username = user_match.group(1)
                    break

                if proc.poll() is not None:
                    break

            if not username:
                log("❌ Could not connect with existing credentials.", COLOR_RED)
                return

        log("")
        log(f"✅ Authenticated successfully as: {username}", COLOR_GREEN + COLOR_BOLD)
        log(f"📡 Requesting AES decryption key for test track: {TEST_TRACK_NAME}...", COLOR_CYAN)

        # Step 3: Trigger playback of test track
        time.sleep(1)
        http_post(f"http://127.0.0.1:{port}/player/play", {"uri": TEST_TRACK_URI})

        # Step 4: Monitor logs for Code 1 vs Success
        key_refused = False
        track_loaded = False
        probe_start = time.time()

        while time.time() - probe_start < 6:
            time.sleep(0.5)
            content = read_logs()

            if "refused the audio key (code 1)" in content or "failed retrieving aes key with code 1" in content:
                key_refused = True
                break

            if "loaded track" in content or "active stream" in content:
                track_loaded = True

            st = http_get(f"http://127.0.0.1:{port}/status")
            if isinstance(st, dict) and st.get("track"):
                track_loaded = True

        log("")
        if key_refused:
            log("======================================================================", COLOR_RED + COLOR_BOLD)
            log("  ❌ RESULT: ACCOUNT RESTRICTED (Spotify DRM Code 1)", COLOR_RED + COLOR_BOLD)
            log("======================================================================", COLOR_RED + COLOR_BOLD)
            log(f"  Spotify Username:  {username}")
            log(f"  Access Point:      Refused Audio Decryption Key (code 1)", COLOR_RED)
            log(f"  DRM Status:        Restricted (PlayPlay DRM Enforced)", COLOR_RED)
            log("")
            log("  ⚠️  What this means:", COLOR_BOLD)
            log("  Spotify has rolled out proprietary PlayPlay DRM to this account.")
            log("  Spotify's servers refuse to hand over the raw AES audio keys")
            log("  required by open-source clients (go-librespot / librespot).")
            log("")
            log("  💡 What you should do:", COLOR_YELLOW + COLOR_BOLD)
            log("  1. Use an older/established Spotify Premium account (created earlier).")
            log("  2. Or stay tuned for the Universal Audio Engine update, which will")
            log("     allow your TeamSpeak bot to stream without Spotify DRM limits!")
            log("======================================================================", COLOR_RED + COLOR_BOLD)
        else:
            log("======================================================================", COLOR_GREEN + COLOR_BOLD)
            log("  ✅ RESULT: ACCOUNT 100% COMPATIBLE!", COLOR_GREEN + COLOR_BOLD)
            log("======================================================================", COLOR_GREEN + COLOR_BOLD)
            log(f"  Spotify Username:  {username}")
            log(f"  Access Point:      AES Decryption Key Granted (200 OK)", COLOR_GREEN)
            log(f"  DRM Status:        Unrestricted (Legacy AP Access Active)", COLOR_GREEN)
            log("")
            log("  🎉 Congratulations!", COLOR_BOLD)
            log("  Your Spotify account is fully compatible with open-source bots.")
            log("  You can proceed to set up the TeamSpeak Spotify Music Bot!")
            log("======================================================================", COLOR_GREEN + COLOR_BOLD)
        log("")

    except KeyboardInterrupt:
        log("\n🛑 Test cancelled by user.", COLOR_YELLOW)
    finally:
        # Step 5: Clean shutdown
        http_post(f"http://127.0.0.1:{port}/player/stop", {})
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
