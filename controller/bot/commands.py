import os, json, time, asyncio, subprocess, logging
from .spotify import to_uri, SpotifyRateLimitError, SpotifyAuthError
from .pulse import set_audio_mute
from .guard import GUARD, ACTION_PLAY, ACTION_PAUSE, ACTION_STOP

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
    def __init__(self, cfg, cq, lr, search, uid, nick, cid, server_groups=None, channel_group=None, is_admin=False, cmd="", app=None):
        self.cfg, self.cq, self.lr, self.search = cfg, cq, lr, search
        self.uid, self.nick, self.cid = uid, nick, cid
        self.server_groups = server_groups or set()
        self.channel_group = channel_group or ""
        self.is_admin = is_admin
        self.cmd = cmd
        self.app = app

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
    except Exception as e:
        log.debug("status check before play: %s", e)
        st = None

    if not st or not st.get("username"):
        return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"

    if not arg:
        if _is_bgm_active(ctx):
            return (
                "☕ [b]Background Music is already playing.[/b]\n"
                f"Type [b]{ctx.cfg.prefix}play <song>[/b] anytime to play your own music!"
            )

        allowed, reason = GUARD.can_toggle_state(ACTION_PLAY, is_admin=ctx.is_admin)
        if not allowed:
            return reason

        async with GUARD.lock:
            await set_audio_mute(False)
            try:
                await asyncio.wait_for(ctx.lr.resume(), timeout=10.0)
            except asyncio.TimeoutError:
                return "⏳ Resume timed out. Spotify may still be connecting."
            except Exception:
                return (
                    "⚠️ [b]Resume Failed:[/b] Spotify was unable to resume playback.\n"
                    f"Check if your Premium subscription is active or type [b]{ctx.cfg.prefix}login[/b] to re-link."
                )
            GUARD.mark_state(ACTION_PLAY)
            return "Resumed."

    uri, label = to_uri(arg), arg
    if not uri:
        try:
            hits = await asyncio.wait_for(ctx.search.tracks(arg, limit=1), timeout=8.0)
        except asyncio.TimeoutError:
            return "⚠️ Spotify search timed out. Try pasting a direct Spotify track or playlist link."
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
        except Exception as e:
            log.warning("Spotify search failed: %s", e)
            return "⚠️ Spotify search is temporarily busy. Try pasting a direct Spotify link instead."
        if not hits:
            return "Nothing found."
        uri, label = hits[0]["uri"], f'{hits[0]["name"]} - {hits[0]["artists"]}'

    allowed, reason = GUARD.can_toggle_state(ACTION_PLAY, is_admin=ctx.is_admin)
    if not allowed:
        return reason

    async with GUARD.lock:
        await set_audio_mute(False)
        try:
            await asyncio.wait_for(ctx.lr.play(uri), timeout=15.0)
        except asyncio.TimeoutError:
            return "⏳ Spotify is taking longer than usual to buffer this track. Please wait a moment."
        except Exception as e:
            log.exception("play failed for uri=%s: %s", uri, e)
            return (
                "⚠️ [b]Playback Failed:[/b] Spotify was unable to stream this track.\n"
                "This usually happens if your [b]Spotify Premium subscription has expired[/b] or the account was logged out.\n"
                f"👉 Please renew your Spotify Premium subscription, or an admin can link a different Premium account using: [b]{ctx.cfg.prefix}login force[/b]"
            )
        was_bgm = getattr(ctx.app, "is_ambient_autoplay", False) if ctx.app else False
        if ctx.app:
            ctx.app._paused_by_empty_channel = False
            ctx.app._ready_for_ambient_autoplay = False
            ctx.app.is_ambient_autoplay = False

        target_vol = getattr(ctx.app, "user_volume", ctx.cfg.initial_volume) if ctx.app else ctx.cfg.initial_volume
        try:
            await ctx.lr.volume(target_vol)
            GUARD.mark_volume(target_vol)
        except Exception:
            pass

        GUARD.mark_state(ACTION_PLAY)
        return f"Playing: {label}"

@command("queue", "q")
async def queue(ctx, arg):
    try:
        st = await ctx.lr.status()
    except Exception as e:
        log.debug("status check before queue: %s", e)
        st = None

    if not st or not st.get("username"):
        return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"

    if not arg:
        return f"Usage: {ctx.cfg.prefix}queue <song name or Spotify link>"

    uri, label = to_uri(arg), arg
    if not uri:
        try:
            hits = await asyncio.wait_for(ctx.search.tracks(arg, limit=1), timeout=8.0)
        except asyncio.TimeoutError:
            return "⚠️ Spotify search timed out. Try pasting a direct Spotify track link."
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
        except Exception as e:
            log.warning("Spotify search failed in queue: %s", e)
            return "⚠️ Spotify search is temporarily busy. Try pasting a direct Spotify link."
        if not hits:
            return "Nothing found."
        uri, label = hits[0]["uri"], f'{hits[0]["name"]} - {hits[0]["artists"]}'

    allowed, reason = GUARD.can_queue_track(ctx.uid, uri, is_admin=ctx.is_admin)
    if not allowed:
        return reason

    async with GUARD.lock:
        try:
            await asyncio.wait_for(ctx.lr.enqueue(uri), timeout=10.0)
            GUARD.mark_queued(ctx.uid, uri)
            return f"Queued: {label}"
        except asyncio.TimeoutError:
            return "⏳ Queue request timed out. Please try again."
        except Exception as e:
            log.exception("queue failed for uri=%s: %s", uri, e)
            return (
                "⚠️ [b]Queue Failed:[/b] Spotify was unable to queue this track.\n"
                "This usually happens if your [b]Spotify Premium subscription has expired[/b] or the account was logged out.\n"
                f"👉 Please renew your Spotify Premium subscription, or an admin can link a different Premium account using: [b]{ctx.cfg.prefix}login force[/b]"
            )

def _is_bgm_active(ctx) -> bool:
    if not ctx.app:
        return False
    return getattr(ctx.app, "is_ambient_autoplay", False)

@command("pause")
async def pause(ctx, arg):
    if _is_bgm_active(ctx):
        return (
            "☕ [b]Background Music is the bot's default idle state and cannot be paused.[/b]\n"
            f"Type [b]{ctx.cfg.prefix}play <song>[/b] anytime to play your own music!"
        )

    allowed, reason = GUARD.can_toggle_state(ACTION_PAUSE, is_admin=ctx.is_admin)
    if not allowed:
        return reason

    # Instantly mute PulseAudio capture/sink for zero-delay hardware silence
    await set_audio_mute(True)

    async with GUARD.lock:
        try:
            st = await ctx.lr.status()
        except Exception as e:
            log.debug("status check before pause: %s", e)
            st = None

        if not st or not st.get("username"):
            await set_audio_mute(False)
            return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"
        try:
            await asyncio.wait_for(ctx.lr.pause(), timeout=8.0)
        except Exception as e:
            log.warning("pause failed, trying playpause fallback: %s", e)
            try:
                await asyncio.wait_for(ctx.lr.playpause(), timeout=8.0)
            except Exception as e2:
                log.exception("pause and playpause failed: %s", e2)
        GUARD.mark_state(ACTION_PAUSE)
        return "⏸️ Playback paused."

@command("stop")
async def stop(ctx, arg):
    if _is_bgm_active(ctx):
        return (
            "☕ [b]Background Music is the bot's default idle state and cannot be stopped.[/b]\n"
            f"Type [b]{ctx.cfg.prefix}play <song>[/b] anytime to play your own music!"
        )

    allowed, reason = GUARD.can_toggle_state(ACTION_STOP, is_admin=ctx.is_admin)
    if not allowed:
        return reason

    app = ctx.app
    has_users = bool(app.channel_clients) if app else True

    # If users are in the channel, returning to default BGM is immediate and mandatory
    if has_users and app and app.spotify_ok:
        async with GUARD.lock:
            await app._return_to_bgm()
            return "⏹️ Playback stopped. Returned to default background music."

    # If channel has no users, stop audio completely
    await set_audio_mute(True)
    async with GUARD.lock:
        try:
            await asyncio.wait_for(ctx.lr.pause(), timeout=8.0)
        except Exception as e:
            log.warning("pause during stop failed: %s", e)
        GUARD.mark_state(ACTION_STOP)
        return "⏹️ Playback stopped."

@command("resume", "r")
async def resume(ctx, arg):
    if _is_bgm_active(ctx):
        return (
            "☕ [b]Background Music is already active.[/b]\n"
            f"Type [b]{ctx.cfg.prefix}play <song>[/b] anytime to play your own music!"
        )

    allowed, reason = GUARD.can_toggle_state(ACTION_PLAY, is_admin=ctx.is_admin)
    if not allowed:
        return reason

    async with GUARD.lock:
        try:
            st = await ctx.lr.status()
        except Exception as e:
            log.debug("status check before resume: %s", e)
            st = None

        if not st or not st.get("username"):
            return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"
        if st and not st.get("paused") and not st.get("stopped"):
            return "Already playing."

        await set_audio_mute(False)
        try:
            await asyncio.wait_for(ctx.lr.resume(), timeout=10.0)
            GUARD.mark_state(ACTION_PLAY)
            return "▶️ Playback resumed."
        except asyncio.TimeoutError:
            return "⏳ Resume timed out. Spotify may still be connecting."
        except Exception:
            return (
                "⚠️ [b]Resume Failed:[/b] Spotify was unable to resume playback.\n"
                f"Check if your Premium subscription is active or type [b]{ctx.cfg.prefix}login[/b] to re-link."
            )

@command("skip", "next", "s")
async def skip(ctx, arg):
    if _is_bgm_active(ctx):
        return (
            "☕ [b]Track controls are disabled for Background Music.[/b]\n"
            f"Type [b]{ctx.cfg.prefix}play <song>[/b] anytime to play your own song!"
        )

    allowed, reason = GUARD.can_skip(is_admin=ctx.is_admin)
    if not allowed:
        return reason

    try:
        st = await ctx.lr.status()
    except Exception:
        st = None

    if not st or not st.get("username"):
        return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"

    async with GUARD.lock:
        GUARD.mark_skip()
        await set_audio_mute(False)
        try:
            await asyncio.wait_for(ctx.lr.next(), timeout=5.0)
            return "⏭️ Skipped to next track."
        except asyncio.TimeoutError:
            return "⏳ Skip timed out. The next track may still be buffering."
        except Exception as e:
            log.warning("skip failed: %s", e)
            return "⚠️ Unable to skip right now. The track may still be loading."

@command("prev", "back")
async def prev(ctx, arg):
    if _is_bgm_active(ctx):
        return (
            "☕ [b]Track controls are disabled for Background Music.[/b]\n"
            f"Type [b]{ctx.cfg.prefix}play <song>[/b] anytime to play your own song!"
        )

    allowed, reason = GUARD.can_skip(is_admin=ctx.is_admin)
    if not allowed:
        return reason

    try:
        st = await ctx.lr.status()
    except Exception:
        st = None

    if not st or not st.get("username"):
        return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"

    async with GUARD.lock:
        GUARD.mark_skip()
        await set_audio_mute(False)
        try:
            await asyncio.wait_for(ctx.lr.prev(), timeout=5.0)
            return "⏮️ Returned to previous track."
        except asyncio.TimeoutError:
            return "⏳ Returning to previous track timed out."
        except Exception as e:
            log.warning("prev failed: %s", e)
            return "⚠️ Unable to return to previous track."

@command("vol", "volume", "v")
async def vol(ctx, arg):
    app = ctx.app
    user_vol = getattr(app, "user_volume", ctx.cfg.initial_volume) if app else ctx.cfg.initial_volume

    if not arg:
        if _is_bgm_active(ctx):
            return f"Current volume: [b]{ctx.cfg.chill_volume}%[/b] (Background Music) | Active music volume set to: [b]{user_vol}%[/b]"
        return f"Current volume: [b]{user_vol}%[/b]"

    arg_clean = arg.strip()
    if arg_clean.startswith(("+", "-")):
        try:
            delta = int(arg_clean)
            target_vol = user_vol + delta
        except ValueError:
            return f"Usage: [b]{ctx.cfg.prefix}vol <0-{ctx.cfg.max_volume}>[/b] (e.g. [b]{ctx.cfg.prefix}vol 60[/b] or [b]{ctx.cfg.prefix}vol +10[/b])"
    else:
        try:
            target_vol = int(arg_clean)
        except ValueError:
            return f"Usage: [b]{ctx.cfg.prefix}vol <0-{ctx.cfg.max_volume}>[/b] (e.g. [b]{ctx.cfg.prefix}vol 60[/b] or [b]{ctx.cfg.prefix}vol +10[/b])"

    target_vol = max(0, min(target_vol, ctx.cfg.max_volume))

    if user_vol == target_vol and not _is_bgm_active(ctx):
        return f"Volume is already {target_vol}%."

    allowed, reason = GUARD.can_adjust_volume(is_admin=ctx.is_admin)
    if not allowed:
        return reason

    if app:
        app.user_volume = target_vol
    GUARD.mark_volume(target_vol)

    if _is_bgm_active(ctx):
        return (
            f"🔊 Music playback volume set to [b]{target_vol}%[/b].\n"
            f"• This will take effect when a song starts playing (e.g. [b]{ctx.cfg.prefix}play <song>[/b]).\n"
            f"• Background music remains locked at [b]{ctx.cfg.chill_volume}%[/b]."
        )

    async with GUARD.lock:
        try:
            await asyncio.wait_for(ctx.lr.volume(target_vol), timeout=5.0)
            return f"Volume set to: {target_vol}%"
        except asyncio.TimeoutError:
            return "⏳ Volume update timed out. Please try again."
        except Exception as e:
            log.warning("Volume change failed: %s", e)
            return "⚠️ Unable to change volume right now."

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

def _get_sys_resources():
    mem = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    mem[parts[0].strip()] = int(parts[1].strip().split()[0])
        tot = mem.get("MemTotal", 0) // 1024
        avail = mem.get("MemAvailable", 0) // 1024
        used = tot - avail
        pct = round((used / tot) * 100, 1) if tot else 0
        sw_tot = mem.get("SwapTotal", 0) // 1024
        sw_free = mem.get("SwapFree", 0) // 1024
        sw_used = sw_tot - sw_free
        sw_pct = round((sw_used / sw_tot) * 100, 1) if sw_tot else 0
    except Exception:
        tot, used, pct = 0, 0, 0
        sw_tot, sw_used, sw_pct = 0, 0, 0

    cpu = "N/A"
    try:
        with open("/proc/loadavg") as f:
            cpu = f.read().split()[0]
    except Exception:
        pass

    uptime = "N/A"
    try:
        with open("/proc/uptime") as f:
            s = int(float(f.read().split()[0]))
            d, rem = divmod(s, 86400)
            h, rem = divmod(rem, 3600)
            m, _ = divmod(rem, 60)
            uptime = f"{d}d {h}h {m}m" if d > 0 else f"{h}h {m}m"
    except Exception:
        pass

    return {
        "ram_used": used, "ram_total": tot, "ram_pct": pct,
        "swap_used": sw_used, "swap_total": sw_tot, "swap_pct": sw_pct,
        "cpu": cpu, "uptime": uptime
    }

@command("status", admin=True)
async def status(ctx, arg):
    sys_res = _get_sys_resources()

    try:
        st = await ctx.lr.status()
    except Exception:
        st = None

    # TeamSpeak channel & client info
    ch_name = "Unknown"
    humans = 0
    if ctx.cid:
        try:
            cv = await ctx.cq.kv(f"channelvariable cid={ctx.cid} channel_name")
            ch_name = cv.get("channel_name", "Unknown").replace("\\s", " ")
        except Exception:
            pass
        try:
            clines = await ctx.cq.cmd(f"channelclientlist cid={ctx.cid}")
            raw = " ".join(clines)
            for chunk in raw.split("|"):
                parts = dict(kv.split("=", 1) for kv in chunk.split() if "=" in kv)
                clid = parts.get("clid")
                ctype = parts.get("client_type")
                if clid and clid != ctx.app.my_clid if ctx.app else True and ctype != "1":
                    humans += 1
        except Exception:
            pass

    # Ducking state
    duck_on = ctx.app.ducking_enabled if ctx.app else False
    duck_pct = getattr(ctx.app, "duck_percent", 30) if ctx.app else 30
    hold_s = getattr(ctx.app, "duck_hold_time", 1.8) if ctx.app else 1.8
    duck_tag = f"[color=#28a745][b]ON[/b][/color] (Dips to {duck_pct}% | Hold: {hold_s:.1f}s)" if duck_on else "[color=#888888][b]OFF[/b][/color]"

    # Spotify info
    if not st or not st.get("username"):
        sp_info = f"• Status: [color=#d9534f]Disconnected[/color] (Type [b]{ctx.cfg.prefix}login[/b] to pair)"
    else:
        user = st.get("username", "Unknown")
        dev = st.get("device_name", "Spotify Device")
        paused = st.get("paused", True)
        state_str = "[color=#f0ad4e]Paused[/color]" if paused else "[color=#28a745]Playing[/color]"
        vol = st.get("volume", ctx.cfg.initial_volume)
        track = st.get("track")
        track_info = ""
        if track and not paused:
            track_name = track.get("name", "Unknown")
            artists_raw = track.get("artist_names", [])
            artist_name = ", ".join(artists_raw) if isinstance(artists_raw, list) else str(artists_raw)
            track_info = f"\n• Track: [b]{track_name}[/b] by {artist_name}"
        sp_info = (f"• Account: [b]{user}[/b] | Device: [b]{dev}[/b]\n"
                   f"• State: {state_str} | Volume: [b]{vol}%[/b]{track_info}")

    return (
        f"📊 [b]Bot & System Health Status[/b]\n"
        f"──────────────────────────────────────\n"
        f"🖥️ [b]System Resources:[/b]\n"
        f"• RAM: [b]{sys_res['ram_used']} MB[/b] / {sys_res['ram_total']} MB ({sys_res['ram_pct']}%)\n"
        f"• Swap: [b]{sys_res['swap_used']} MB[/b] / {sys_res['swap_total']} MB ({sys_res['swap_pct']}%)\n"
        f"• CPU Load: [b]{sys_res['cpu']}[/b] | Uptime: [b]{sys_res['uptime']}[/b]\n\n"
        f"🎙️ [b]TeamSpeak 3:[/b]\n"
        f"• Channel: [b]{ch_name}[/b] (Users: [b]{humans}[/b])\n"
        f"• Voice Ducking: {duck_tag}\n\n"
        f"🎵 [b]Spotify Connect:[/b]\n"
        f"{sp_info}\n"
        f"──────────────────────────────────────"
    )

@command("duck", "ducking")
async def duck(ctx, arg):
    app = ctx.app
    if not app:
        return "Audio ducking controller unavailable."

    raw = arg.strip().lower()
    from .pulse import set_audio_duck

    # Check if setting conversation hold time (e.g. !duck hold 2.0, !duck delay 1.5)
    if raw.startswith("hold") or raw.startswith("delay") or raw.startswith("window"):
        parts = raw.split()
        if len(parts) >= 2:
            try:
                sec = float(parts[1].rstrip("s"))
                if not (0.5 <= sec <= 10.0):
                    return "⚠️ Hold window must be between [b]0.5[/b] and [b]10.0[/b] seconds (e.g. [b]!duck hold 2.0[/b])."
                app.duck_hold_time = sec
                return (
                    f"⏱️ Voice Ducking conversation hold window set to [b]{sec:.1f}s[/b].\n"
                    f"Music volume will stay lowered during conversational pauses and only restore after [b]{sec:.1f}s[/b] of sustained silence."
                )
            except ValueError:
                pass
        return f"Usage: [b]{ctx.cfg.prefix}duck hold <seconds>[/b] (e.g. [b]{ctx.cfg.prefix}duck hold 2.0[/b])"

    # Check if a custom ducking percentage is passed (e.g. !duck 20, !duck 15%)
    val_str = raw.rstrip("%")
    if val_str.isdigit():
        target = int(val_str)
        if not (5 <= target <= 90):
            return "⚠️ Ducking volume must be between [b]5%[/b] and [b]90%[/b] (e.g. [b]!duck 20[/b])."
        app.duck_percent = target
        app.ducking_enabled = True
        if getattr(app, "speaking_clients", None):
            await set_audio_duck(True, target)
            app._is_ducked = True
        hold_s = getattr(app, "duck_hold_time", 1.8)
        return (
            f"🎙️ Voice Ducking volume set to [b]{target}%[/b] ([color=#28a745][b]ON[/b][/color]).\n"
            f"Music will dip to {target}% volume whenever someone speaks (hold window: [b]{hold_s:.1f}s[/b])."
        )

    if raw in ("on", "1", "enable", "true"):
        app.ducking_enabled = True
        if getattr(app, "speaking_clients", None):
            await set_audio_duck(True, getattr(app, "duck_percent", 30))
            app._is_ducked = True
    elif raw in ("off", "0", "disable", "false"):
        app.ducking_enabled = False
        if hasattr(app, "_cancel_unduck_timer"):
            app._cancel_unduck_timer()
        await set_audio_duck(False)
        app._is_ducked = False
    elif not raw:
        app.ducking_enabled = not app.ducking_enabled
        if not app.ducking_enabled:
            if hasattr(app, "_cancel_unduck_timer"):
                app._cancel_unduck_timer()
            await set_audio_duck(False)
            app._is_ducked = False
        elif getattr(app, "speaking_clients", None):
            await set_audio_duck(True, getattr(app, "duck_percent", 30))
            app._is_ducked = True
    else:
        return (
            f"Usage: [b]{ctx.cfg.prefix}duck [on|off|<5-90>|hold <sec>][/b]\n"
            f"Examples: [b]{ctx.cfg.prefix}duck on[/b], [b]{ctx.cfg.prefix}duck 20[/b], [b]{ctx.cfg.prefix}duck hold 2.0[/b]"
        )

    duck_pct = getattr(app, "duck_percent", 30)
    hold_s = getattr(app, "duck_hold_time", 1.8)
    state = "[color=#28a745][b]ON[/b][/color]" if app.ducking_enabled else "[color=#888888][b]OFF[/b][/color]"
    detail = (
        f"Music volume will dip to {duck_pct}% on speech and hold for {hold_s:.1f}s after speaking stops."
        if app.ducking_enabled
        else "Music volume will stay constant."
    )
    if _is_bgm_active(ctx):
        detail += "\n(Note: Background music is unaffected by ducking; this will take effect when songs are played)."
    return f"🎙️ Voice Ducking is now {state}. {detail}"

@command("chill", "bgm", "ambient")
async def chill(ctx, arg):
    try:
        st = await ctx.lr.status()
    except Exception as e:
        log.debug("status check before chill: %s", e)
        st = None

    if not st or not st.get("username"):
        return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"

    allowed, reason = GUARD.can_toggle_state(ACTION_PLAY, is_admin=ctx.is_admin)
    if not allowed:
        return reason

    if ctx.app:
        ctx.app.is_ambient_autoplay = True
        ctx.app._paused_by_empty_channel = False
        ctx.app._ready_for_ambient_autoplay = False

    async with GUARD.lock:
        try:
            await ctx.lr.volume(ctx.cfg.chill_volume)
            GUARD.mark_volume(ctx.cfg.chill_volume)
            await set_audio_mute(False)
            await ctx.lr.play(ctx.cfg.chill_autoplay_uri)
            GUARD.mark_state(ACTION_PLAY)
            return (
                f"☕ [b]Chill Background Music started[/b] at [b]{ctx.cfg.chill_volume}%[/b] volume.\n"
                f"• Volume is locked to {ctx.cfg.chill_volume}% and voice ducking is disabled for BGM.\n"
                f"• Type [b]{ctx.cfg.prefix}play <song>[/b] anytime to play regular songs and unlock full volume!"
            )
        except Exception as e:
            log.warning("chill command failed: %s", e)
            return "⚠️ Unable to start chill background music."

@command("help", "h")
async def help_(ctx, arg):
    p = ctx.cfg.prefix
    return (f"{p}play <name|link>, {p}queue <name|link>, {p}chill, {p}pause, {p}resume, {p}skip, "
            f"{p}prev, {p}vol <0-{ctx.cfg.max_volume}>, {p}np, {p}duck, {p}login, {p}spotifykeys, {p}myroles | "
            f"admin: {p}logout, {p}restart, {p}reconnect, {p}audio, {p}status")
