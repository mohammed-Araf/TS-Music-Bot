import os, json, asyncio, logging, time
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
        clid = f.get("invokerid")
        uid, nick = f.get("invokeruid", ""), f.get("invokername", "?")

        # Query user's server groups and channel group from client cache
        user_groups = set()
        ch_group = ""
        if clid:
            try:
                cv = await self.cq.kv(f"clientvariable clid={clid} client_servergroups client_channel_group_id")
                raw_groups = cv.get("client_servergroups", "")
                user_groups = set(g.strip() for g in raw_groups.split(",") if g.strip())
                ch_group = cv.get("client_channel_group_id", "")
            except Exception:
                pass

        is_admin = (uid in CFG.admin_uids) or bool(user_groups & CFG.admin_server_groups)
        cmd_lower = cmd.lower()

        if admin_only and not is_admin:
            await self.cq.say(self.my_cid, "Admins only.")
            return

        # Check playback role requirement (exempt admins and info commands)
        if (
            CFG.allowed_server_groups
            and not is_admin
            and cmd_lower not in ("myroles", "roles", "help", "h")
            and not bool(user_groups & CFG.allowed_server_groups)
        ):
            await self.cq.say(self.my_cid, "You need the music role to use this bot.")
            return

        now = time.time()
        if now - self.last_cmd.get(uid, 0) < CFG.cooldown:
            return
        ctx = Ctx(CFG, self.cq, self.lr, self.search, uid, nick, self.my_cid,
                  server_groups=user_groups, channel_group=ch_group, is_admin=is_admin, cmd=cmd_lower)
        try:
            reply = await handler(ctx, arg.strip())
        except Exception as e:
            log.exception("command failed: %s", cmd)
            reply = f"Error: {e}"
        if reply:
            await self.cq.say(self.my_cid, reply)

    async def _resolve_target_cid(self):
        if not CFG.ts_channel:
            return None
        target = CFG.ts_channel.strip()
        leaf = target.split("/")[-1].strip()
        try:
            lines = await self.cq.cmd("channellist")
            raw = " ".join(lines)
            for part in raw.split("|"):
                parts = dict(kv.split("=", 1) for kv in part.split() if "=" in kv)
                cname = parts.get("channel_name", "").replace("\\s", " ").replace("\\/", "/")
                if cname == leaf or cname == target:
                    return parts.get("cid")
        except Exception as e:
            log.warning("Failed to resolve target channel: %s", e)
        return None

    async def _ensure_channel(self):
        if not CFG.ts_channel or not self.my_clid:
            return
        cid = await self._resolve_target_cid()
        if cid and self.my_cid != cid:
            cmd = f"clientmove cid={cid} clid={self.my_clid}"
            if CFG.ts_channel_password:
                cmd += f" cpw={CFG.ts_channel_password}"
            try:
                await self.cq.cmd(cmd)
                self.my_cid = cid
                log.info("Moved bot to channel cid=%s", cid)
            except Exception as e:
                log.warning("Failed to move bot to channel cid=%s: %s", cid, e)

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
                if self.ts_ok:
                    await self._ensure_channel()
            except (QueryError, asyncio.TimeoutError):
                self.ts_ok = False
            await asyncio.sleep(5)

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
        was_ok = False
        consecutive_failures = 0
        while True:
            try:
                st = await self.lr.status()
                now_ok = bool(st and st.get("username"))
                if now_ok:
                    consecutive_failures = 0
                    self.spotify_ok = True
                    was_ok = True
                else:
                    consecutive_failures += 1
                    # Explicit 204 No Content returned repeatedly: real logout
                    if consecutive_failures >= 3:
                        self.spotify_ok = False
                        if was_ok and self.my_cid:
                            try:
                                await self.cq.say(
                                    self.my_cid,
                                    f"⚠️ [b]Spotify Session Ended:[/b] The linked account disconnected or Premium subscription ended.\n"
                                    f"👉 Type [b]{CFG.prefix}login[/b] in chat to reconnect or pair an active Premium account!"
                                )
                            except Exception:
                                pass
                            was_ok = False
            except Exception as e:
                # Backend is busy loading a track or processing a command: do not panic
                log.debug("spotify_loop probe exception: %s", e)
                consecutive_failures += 1
                if consecutive_failures >= 4:
                    self.spotify_ok = False
            await asyncio.sleep(15)

    async def health(self, request):
        ok = self.ts_ok and self.spotify_ok
        return web.json_response({"ts": self.ts_ok, "spotify": self.spotify_ok},
                                 status=200 if ok else 503)

    async def run(self):
        self.session = aiohttp.ClientSession()
        self.lr = Librespot(CFG.lr_url, self.session)
        custom_keys = None
        if os.path.exists("/data/spotify_keys.json"):
            try:
                with open("/data/spotify_keys.json") as f:
                    custom_keys = json.load(f)
            except Exception:
                pass
        cid = (custom_keys.get("client_id") if custom_keys else None) or CFG.sp_client_id
        secret = (custom_keys.get("client_secret") if custom_keys else None) or CFG.sp_client_secret
        self.search = Search(cid, secret, self.session)

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
                await self.lr.volume(CFG.initial_volume)
                return
            except Exception:
                await asyncio.sleep(2)
