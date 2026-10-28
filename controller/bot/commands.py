import os, json, time, asyncio, subprocess, logging
from .spotify import to_uri, SpotifyRateLimitError, SpotifyAuthError
from .pulse import set_audio_mute

log = logging.getLogger("commands")

REGISTRY = {}   # name -> (handler, admin_only)
_pairing_task = None
_keys_wizard = {}  # { "uid": str, "step": str, "client_id": str, "time": float }

KEYS_FILE = "/data/spotify_keys.json"

def save_custom_keys(client_id, client_secret):
    with open(KEYS_FILE, "w") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret}, f)

def remove_custom_keys():
    if os.path.exists(KEYS_FILE):
        try:
            os.remove(KEYS_FILE)
        except Exception:
            pass

def command(name, *aliases, admin=False):
    def deco(fn):
        for n in (name, *aliases):
            REGISTRY[n] = (fn, admin)
        return fn
    return deco

class Ctx:
    def __init__(self, cfg, cq, lr, search, uid, nick, cid, server_groups=None, channel_group=None, is_admin=False, cmd=""):
        self.cfg, self.cq, self.lr, self.search = cfg, cq, lr, search
        self.uid, self.nick, self.cid = uid, nick, cid
        self.server_groups = server_groups or set()
        self.channel_group = channel_group or ""
        self.is_admin = is_admin
        self.cmd = cmd

def _supervisor(*args):
    return subprocess.run(
        ["supervisorctl", "-c", "/opt/bot/docker/supervisord.conf", *args],
        capture_output=True, text=True, timeout=20
    )

# ---------------- music commands ----------------
@command("play", "p")
async def play(ctx, arg):
    try:
        st = await ctx.lr.status()
        if st is not None and not st.get("username"):
            return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"
    except Exception as e:
        log.debug("status check before play: %s", e)

    if not arg:
        await set_audio_mute(False)
        try:
            await ctx.lr.resume()
        except Exception:
            return (
                "⚠️ [b]Resume Failed:[/b] Spotify was unable to resume playback.\n"
                f"Check if your Premium subscription is active or type [b]{ctx.cfg.prefix}login[/b] to re-link."
            )
        return "Resumed."
    uri, label = to_uri(arg), arg
    if not uri:
        try:
            hits = await ctx.search.tracks(arg, limit=1)
        except SpotifyRateLimitError:
            return (
                "⚠️ [b]Spotify Search Rate Limit Reached![/b]\n"
                "• The shared search key has reached its request limit for now.\n"
                "• You can still paste [b]direct Spotify song or playlist links[/b] to play with zero limits!\n"
                f"• Or type [b]{ctx.cfg.prefix}spotifykeys[/b] for a 1-minute step-by-step guide to add your own free key."
            )
        except SpotifyAuthError:
            return (
                "⚠️ [b]Spotify Search Error:[/b] Search credentials are invalid or not configured.\n"
                "• Paste a [b]direct Spotify song/playlist link[/b] to play immediately, or\n"
                f"• Type [b]{ctx.cfg.prefix}spotifykeys[/b] to set up free search keys step-by-step!"
            )
        if not hits:
            return "Nothing found."
        uri, label = hits[0]["uri"], f'{hits[0]["name"]} - {hits[0]["artists"]}'
    await set_audio_mute(False)
    try:
        await ctx.lr.play(uri)
    except Exception as e:
        log.exception("play failed for uri=%s: %s", uri, e)
        return (
            "⚠️ [b]Playback Failed:[/b] Spotify was unable to stream this track.\n"
            "This usually happens if your [b]Spotify Premium subscription has expired[/b] or the account was logged out.\n"
            f"👉 Please renew your Spotify Premium subscription, or an admin can link a different Premium account using: [b]{ctx.cfg.prefix}login force[/b]"
        )
    return f"Playing: {label}"

@command("queue", "q")
async def queue(ctx, arg):
    try:
        st = await ctx.lr.status()
        if st is not None and not st.get("username"):
            return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"
    except Exception as e:
        log.debug("status check before queue: %s", e)

    if not arg:
        return f"Usage: {ctx.cfg.prefix}queue <song name or Spotify link>"
    uri, label = to_uri(arg), arg
    if not uri:
        try:
            hits = await ctx.search.tracks(arg, limit=1)
        except SpotifyRateLimitError:
            return (
                "⚠️ [b]Spotify Search Rate Limit Reached![/b]\n"
                "• The shared search key has reached its request limit for now.\n"
                "• You can still paste [b]direct Spotify song or playlist links[/b] to play with zero limits!\n"
                f"• Or type [b]{ctx.cfg.prefix}spotifykeys[/b] for a 1-minute step-by-step guide to add your own free key."
            )
        except SpotifyAuthError:
            return (
                "⚠️ [b]Spotify Search Error:[/b] Search credentials are invalid or not configured.\n"
                "• Paste a [b]direct Spotify song/playlist link[/b] to play immediately, or\n"
                f"• Type [b]{ctx.cfg.prefix}spotifykeys[/b] to set up free search keys step-by-step!"
            )
        if not hits:
            return "Nothing found."
        uri, label = hits[0]["uri"], f'{hits[0]["name"]} - {hits[0]["artists"]}'
    try:
        await ctx.lr.enqueue(uri)
    except Exception as e:
        log.exception("queue failed for uri=%s: %s", uri, e)
        return (
            "⚠️ [b]Queue Failed:[/b] Spotify was unable to queue this track.\n"
            "This usually happens if your [b]Spotify Premium subscription has expired[/b] or the account was logged out.\n"
            f"👉 Please renew your Spotify Premium subscription, or an admin can link a different Premium account using: [b]{ctx.cfg.prefix}login force[/b]"
        )
    return f"Queued: {label}"

@command("pause")
async def pause(ctx, arg):
    # Instantly mute PulseAudio capture/sink for zero-delay hardware silence
    await set_audio_mute(True)
    try:
        st = await ctx.lr.status()
        if st is not None and not st.get("username"):
            await set_audio_mute(False)
            return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"
    except Exception as e:
        log.debug("status check before pause: %s", e)
    try:
        await ctx.lr.pause()
        return "⏸️ Playback paused."
    except Exception as e:
        log.warning("pause failed, trying playpause fallback: %s", e)
        try:
            await ctx.lr.playpause()
            return "⏸️ Playback paused."
        except Exception as e2:
            log.exception("pause and playpause failed: %s", e2)
            return "⏸️ Playback paused."

@command("stop")
async def stop(ctx, arg):
    # Instantly mute PulseAudio capture/sink for immediate silence
    await set_audio_mute(True)
    try:
        st = await ctx.lr.status()
        if st is not None and not st.get("username"):
            await set_audio_mute(False)
            return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"
    except Exception as e:
        log.debug("status check before stop: %s", e)
    try:
        await ctx.lr.pause()
    except Exception as e:
        log.warning("pause during stop failed: %s", e)
    return "⏹️ Playback stopped."

@command("resume", "r")
async def resume(ctx, arg):
    await set_audio_mute(False)
    try:
        st = await ctx.lr.status()
        if st is not None and not st.get("username"):
            return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"
        if st and not st.get("paused") and not st.get("stopped"):
            return "Already playing."
    except Exception as e:
        log.debug("status check before resume: %s", e)
    try:
        await ctx.lr.resume()
        return "▶️ Playback resumed."
    except Exception:
        return (
            "⚠️ [b]Resume Failed:[/b] Spotify was unable to resume playback.\n"
            f"Check if your Premium subscription is active or type [b]{ctx.cfg.prefix}login[/b] to re-link."
        )

_last_skip_time = 0.0

@command("skip", "next", "s")
async def skip(ctx, arg):
    global _last_skip_time
    now = time.time()
    if now - _last_skip_time < 1.5:
        return "⏳ Skip already in progress..."
    _last_skip_time = now
    await set_audio_mute(False)
    try:
        await ctx.lr.next()
        return "⏭️ Skipped to next track."
    except Exception as e:
        log.warning("skip failed: %s", e)
        return "⚠️ Unable to skip right now. The track may still be loading."

@command("prev", "back")
async def prev(ctx, arg):
    await set_audio_mute(False)
    try:
        await ctx.lr.prev()
        return "⏮️ Returned to previous track."
    except Exception as e:
        log.warning("prev failed: %s", e)
        return "⚠️ Unable to return to previous track."

@command("vol", "volume", "v")
async def vol(ctx, arg):
    try:
        v = max(0, min(int(arg), ctx.cfg.max_volume))
    except ValueError:
        return f"Usage: vol <0-{ctx.cfg.max_volume}>"
    await ctx.lr.volume(v)
    return f"Volume: {v}"

@command("np", "now")
async def np(ctx, arg):
    try:
        st = await ctx.lr.status()
    except Exception:
        st = None
    if not st or not st.get("username"):
        return f"Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] to link an account."
    t = st.get("track")
    if not t:
        return "Nothing playing."
    artists_raw = t.get("artists") or t.get("artist_names", [])
    if isinstance(artists_raw, list):
        if artists_raw and isinstance(artists_raw[0], dict):
            artists = ", ".join(a.get("name", "") for a in artists_raw)
        else:
            artists = ", ".join(str(a) for a in artists_raw)
    else:
        artists = str(artists_raw)
    state = "paused" if st.get("paused") else "playing"
    return f'{state}: {t.get("name", "?")} - {artists}'

@command("myroles", "roles")
async def myroles(ctx, arg):
    groups = ", ".join(sorted(ctx.server_groups)) if ctx.server_groups else "none"
    return f"{ctx.nick} | UID: {ctx.uid} | Server Groups: [{groups}] | Channel Group: {ctx.channel_group or 'none'}"

# ---------------- spotify auth & keys ----------------
async def _poll_for_pairing(ctx, timeout=300):
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < timeout:
        await asyncio.sleep(4)
        try:
            st = await ctx.lr.status()
            if st and st.get("username"):
                await ctx.cq.say(
                    ctx.cid,
                    f"✅ [b]Spotify Connected![/b] Successfully paired as [b]{st.get('username')}[/b]. Ready to play music!"
                )
                return
        except Exception:
            pass
    try:
        await ctx.cq.say(ctx.cid, f"⌛ Spotify pairing code expired. Type [b]{ctx.cfg.prefix}login[/b] to generate a new link.")
    except Exception:
        pass

@command("login", "pair")
async def login(ctx, arg):
    global _pairing_task
    force = arg.strip().lower() == "force"

    st = None
    try:
        st = await ctx.lr.status()
    except Exception:
        pass

    is_logged_in = bool(st and st.get("username"))

    if is_logged_in and not force:
        return (
            f"Spotify is already connected as [b]{st.get('username')}[/b].\n"
            f"To switch or re-link an account, an admin can type [b]{ctx.cfg.prefix}login force[/b] or [b]{ctx.cfg.prefix}logout[/b]."
        )

    if is_logged_in and force and not ctx.is_admin:
        return "Only server admins can force re-link an active Spotify account."

    state_file = "/data/librespot/state.json"
    if force or not is_logged_in:
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except Exception as e:
                return f"Failed to reset credentials: {e}"
        _supervisor("restart", "go-librespot")

    code_info = None
    for _ in range(8):
        await asyncio.sleep(1.0)
        try:
            code_info = await ctx.lr.auth_code()
            if code_info and code_info.get("url"):
                break
        except Exception:
            pass

    if not code_info or not code_info.get("url"):
        return "Failed to get pairing code from Spotify. Please try again in a few moments."

    url = code_info["url"]
    code = code_info.get("code", "")

    if _pairing_task and not _pairing_task.done():
        _pairing_task.cancel()
    _pairing_task = asyncio.create_task(_poll_for_pairing(ctx))

    return (
        f"🔗 [b]Pair Spotify:[/b] Open [url]{url}[/url]\n"
        f"Pairing Code: [b]{code}[/b] (valid for 5 minutes)\n"
        f"Open the link on your phone/PC browser and tap 'Confirm'. The bot will connect automatically once approved!"
    )

@command("logout", admin=True)
async def logout(ctx, arg):
    state_file = "/data/librespot/state.json"
    if os.path.exists(state_file):
        try:
            os.remove(state_file)
        except Exception as e:
            return f"Failed to unlink credentials: {e}"
    _supervisor("restart", "go-librespot")
    return f"Spotify unlinked. To connect a new account, type [b]{ctx.cfg.prefix}login[/b]."

@command("spotifykeys", "keys", "setkeys")
async def spotifykeys(ctx, arg):
    global _keys_wizard
    p = ctx.cfg.prefix
    sub = arg.strip()
    now = time.time()

    # Cancel command
    if sub.lower() in ("cancel", "stop", "abort"):
        _keys_wizard = {}
        return "❌ Spotify keys setup cancelled."

    # Reset command
    if sub.lower() in ("reset", "default"):
        remove_custom_keys()
        ctx.search.set_credentials(ctx.cfg.sp_client_id, ctx.cfg.sp_client_secret)
        _keys_wizard = {}
        return "🔄 Reverted to the default built-in Spotify search credentials."

    # Direct 2-arg mode: !spotifykeys <client_id> <client_secret>
    parts = sub.split()
    if len(parts) == 2 and not any(parts[0].lower() == kw for kw in ("ready", "id", "secret")):
        cid, secret = parts[0].strip(), parts[1].strip()
        try:
            await ctx.search.verify(cid, secret)
        except SpotifyAuthError as e:
            return f"❌ Verification Failed: {e}"
        except SpotifyRateLimitError:
            return "⚠️ Rate limit reached during verification. Please wait a moment and try again."
        save_custom_keys(cid, secret)
        ctx.search.set_credentials(cid, secret)
        _keys_wizard = {}
        return "✅ [b]Success![/b] Your custom Spotify Search keys were verified and activated!"

    # Expire wizard session after 10 minutes
    wizard = _keys_wizard
    if wizard and now - wizard.get("time", 0) > 600:
        wizard = _keys_wizard = {}

    current_step = wizard.get("step") if wizard else None

    # Step 1: Initial call without args or starting over
    if not current_step or sub.lower() in ("start", "new", "begin") or (not sub and current_step == "ready"):
        _keys_wizard = {
            "uid": ctx.uid,
            "step": "ready",
            "client_id": None,
            "time": now
        }
        return (
            "🔑 [b]Step 1/3: Get your free Spotify Developer Keys[/b]\n"
            "1. Open [url]https://developer.spotify.com/dashboard[/url] in your browser.\n"
            "2. Log in with any free Spotify account & click [b]'Create App'[/b].\n"
            "3. Enter any App name (e.g. 'MyBot'), select 'Web API', and click Save.\n"
            "4. Click [b]'Settings'[/b] to see your Client ID and Client Secret.\n\n"
            f"👉 When you have that page open, reply with: [b]{p}spotifykeys ready[/b]\n"
            f"(Or type [b]{p}spotifykeys cancel[/b] to abort)"
        )

    # Step 2: User says ready -> prompt for Client ID
    if current_step == "ready" and sub.lower() == "ready":
        _keys_wizard["step"] = "client_id"
        _keys_wizard["time"] = now
        return (
            "🔑 [b]Step 2/3: Enter your Client ID[/b]\n"
            "On your Spotify Dashboard Settings, copy your [b]Client ID[/b] (32-character code).\n\n"
            f"👉 Reply with: [b]{p}spotifykeys <YOUR_CLIENT_ID>[/b]\n"
            f"(Example: {p}spotifykeys 4c1a8e7b92f0...)"
        )

    # Step 2: User submits Client ID
    if current_step == "client_id":
        cid = sub
        if cid.lower().startswith("id "):
            cid = cid[3:].strip()
        if len(cid) < 16 or " " in cid:
            return (
                "⚠️ That doesn't look like a valid Client ID (should be ~32 alphanumeric characters with no spaces).\n"
                f"Please copy the Client ID from developer.spotify.com and reply:\n"
                f"👉 [b]{p}spotifykeys <YOUR_CLIENT_ID>[/b]"
            )
        _keys_wizard["client_id"] = cid
        _keys_wizard["step"] = "client_secret"
        _keys_wizard["time"] = now
        return (
            "🔑 [b]Step 3/3: Enter your Client Secret[/b]\n"
            f"Client ID received: [b]{cid[:6]}...{cid[-4:]}[/b]\n"
            "Now on Spotify Dashboard Settings, click [b]'View client secret'[/b] and copy it.\n\n"
            f"👉 Reply with: [b]{p}spotifykeys <YOUR_CLIENT_SECRET>[/b]"
        )

    # Step 3: User submits Client Secret -> verify and activate
    if current_step == "client_secret":
        secret = sub
        if secret.lower().startswith("secret "):
            secret = secret[7:].strip()
        if len(secret) < 16 or " " in secret:
            return (
                "⚠️ That doesn't look like a valid Client Secret (should be ~32 alphanumeric characters with no spaces).\n"
                f"Please copy the Client Secret from developer.spotify.com and reply:\n"
                f"👉 [b]{p}spotifykeys <YOUR_CLIENT_SECRET>[/b]"
            )
        cid = _keys_wizard.get("client_id")
        if not cid:
            _keys_wizard["step"] = "client_id"
            return f"⚠️ Missing Client ID. Please start Step 2 again: [b]{p}spotifykeys <CLIENT_ID>[/b]"

        # Live verification with Spotify Web API
        try:
            await ctx.search.verify(cid, secret)
        except SpotifyAuthError:
            return (
                "❌ [b]Verification Failed:[/b] Spotify rejected these credentials (invalid Client ID or Secret).\n"
                "Please double check your keys on developer.spotify.com and try pasting the secret again:\n"
                f"👉 [b]{p}spotifykeys <YOUR_CLIENT_SECRET>[/b]\n"
                f"(Or type [b]{p}spotifykeys cancel[/b] to abort)"
            )
        except SpotifyRateLimitError:
            return "⚠️ Spotify rate limit reached during verification. Please wait a few seconds and try again."

        save_custom_keys(cid, secret)
        ctx.search.set_credentials(cid, secret)
        _keys_wizard = {}
        return (
            "✅ [b]Success! Spotify Search Keys Verified & Activated![/b]\n"
            "Your custom developer credentials have been saved. You can now search and play songs anytime (e.g. !play Bohemian Rhapsody) with your own dedicated quota!"
        )

    return f"Type [b]{p}spotifykeys[/b] to start the setup guide, or [b]{p}spotifykeys cancel[/b] to exit."

# ---------------- bot control (admin) ----------------
@command("restart", admin=True)
async def restart(ctx, arg):
    # Stops supervisord, so the container exits and Docker's restart policy brings it back.
    asyncio.get_running_loop().call_later(1.5, lambda: _supervisor("shutdown"))
    return "Restarting container..."

@command("reconnect", admin=True)
async def reconnect(ctx, arg):
    try:
        url = open("/tmp/ts_url").read().strip()
        subprocess.run(["/opt/ts3client/ts3client_runscript.sh", url],
                       capture_output=True, text=True, timeout=20)
        return "Reconnect requested."
    except Exception as e:
        return f"Reconnect failed: {e}"

@command("audio", admin=True)
async def audio(ctx, arg):
    r = _supervisor("restart", "go-librespot")
    return "Audio backend restarted." if r.returncode == 0 else f"Failed: {r.stdout.strip()}"

@command("status", admin=True)
async def status(ctx, arg):
    try:
        st = await ctx.lr.status()
    except Exception:
        st = None
    if not st or not st.get("username"):
        return f"Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] to pair."
    return f"Spotify connected as {st.get('username')}; paused={st.get('paused')}; volume={st.get('volume')}"

@command("help", "h")
async def help_(ctx, arg):
    p = ctx.cfg.prefix
    return (f"{p}play <name|link>, {p}queue <name|link>, {p}pause, {p}resume, {p}skip, "
            f"{p}prev, {p}vol <0-{ctx.cfg.max_volume}>, {p}np, {p}login, {p}spotifykeys, {p}myroles | "
            f"admin: {p}logout, {p}restart, {p}reconnect, {p}audio, {p}status")
