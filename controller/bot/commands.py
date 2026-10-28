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

# ---------------- music commands ----------------
@command("play", "p")
async def play(ctx, arg):
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
    st = await ctx.lr.status()
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
    try:
        url = open("/tmp/ts_url").read().strip()
        _sh("/opt/ts3client/ts3client_runscript.sh", url)
        return "Reconnect requested."
    except Exception as e:
        return f"Reconnect failed: {e}"

@command("audio", admin=True)
async def audio(ctx, arg):
    r = _sh("supervisorctl", "restart", "go-librespot")
    return "Audio backend restarted." if r.returncode == 0 else f"Failed: {r.stdout.strip()}"

@command("status", admin=True)
async def status(ctx, arg):
    st = await ctx.lr.status()
    return f"Spotify API ok; paused={st.get('paused')}; volume={st.get('volume')}"
