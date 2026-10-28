import os, asyncio, subprocess, logging
from .spotify import to_uri

log = logging.getLogger("commands")

REGISTRY = {}   # name -> (handler, admin_only)
_pairing_task = None

def command(name, *aliases, admin=False):
    def deco(fn):
        for n in (name, *aliases):
            REGISTRY[n] = (fn, admin)
        return fn
    return deco

class Ctx:
    def __init__(self, cfg, cq, lr, search, uid, nick, cid, server_groups=None, channel_group=None, is_admin=False):
        self.cfg, self.cq, self.lr, self.search = cfg, cq, lr, search
        self.uid, self.nick, self.cid = uid, nick, cid
        self.server_groups = server_groups or set()
        self.channel_group = channel_group or ""
        self.is_admin = is_admin

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
    except Exception:
        st = None
    if not st or not st.get("username"):
        return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"

    if not arg:
        await ctx.lr.resume()
        return "Resumed."
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
    try:
        st = await ctx.lr.status()
    except Exception:
        st = None
    if not st or not st.get("username"):
        return f"⚠️ Spotify is not connected. Type [b]{ctx.cfg.prefix}login[/b] in chat to link an account!"

    if not arg:
        return f"Usage: {ctx.cfg.prefix}queue <song name or Spotify link>"
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
    await ctx.lr.pause()
    return "Paused."

@command("resume", "r")
async def resume(ctx, arg):
    await ctx.lr.resume()
    return "Resumed."

@command("skip", "next", "s")
async def skip(ctx, arg):
    await ctx.lr.next()
    return "Skipped."

@command("prev", "back")
async def prev(ctx, arg):
    await ctx.lr.prev()
    return "Previous track."

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

# ---------------- spotify auth commands ----------------
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
            f"{p}prev, {p}vol <0-{ctx.cfg.max_volume}>, {p}np, {p}login, {p}myroles | "
            f"admin: {p}logout, {p}restart, {p}reconnect, {p}audio, {p}status")
